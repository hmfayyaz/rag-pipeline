import os
import shutil
from pathlib import Path
from uuid import UUID
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.user import User, UserRole
from app.db.models.organization import Organization, OrganizationMember, OrgRole, Invitation
from app.db.models.rag_document import RAGDocument
from app.db.models.conversation import Conversation, Message, ToolCall
from app.db.models.message_rating import MessageRating
from app.db.models.sync_log import SyncLog
from app.db.models.sync_source import SyncSource

from app.schemas.user import UserCreate
from app.services.user import UserService
from app.services.rag_document import RAGDocumentService
from app.services.rag.ingestion import IngestionService
from app.services.rag.vectorstore import QdrantVectorStore
from app.services.rag.embeddings import EmbeddingService


class DevSeedingService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_service = UserService(db)
        self.rag_doc_service = RAGDocumentService(db)

    async def reset_everything(self) -> None:
        """Clear all Qdrant vectors and delete PostgreSQL records in reverse dependency order."""
        # 1. Clear Qdrant
        embedder = EmbeddingService(settings=settings.rag)
        vector_store = QdrantVectorStore(settings=settings.rag, embedding_service=embedder)
        try:
            collections = await vector_store.list_collections()
            for col in collections:
                await vector_store.delete_collection(col)
        except Exception as e:
            # Qdrant might be offline or empty
            pass
        finally:
            await vector_store.client.close()

        # 2. Clear postgres tables
        await self.db.execute(delete(SyncLog))
        await self.db.execute(delete(RAGDocument))
        await self.db.execute(delete(SyncSource))
        await self.db.execute(delete(MessageRating))
        await self.db.execute(delete(ToolCall))
        await self.db.execute(delete(Message))
        await self.db.execute(delete(Conversation))
        await self.db.execute(delete(Invitation))
        await self.db.execute(delete(OrganizationMember))
        
        # Delete organizations
        await self.db.execute(delete(Organization))
        
        # Delete all users except app admins
        await self.db.execute(delete(User).where(User.role != UserRole.ADMIN.value))
        
        await self.db.commit()

        # Clean up temporary media directory
        tmp_dir = os.path.join(str(settings.MEDIA_DIR), "_rag_tmp")
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def seed_demo_data(self) -> dict:
        """Seed Tenants, Users for every tenant role, and upload 20 mock documents in each tenant."""
        # First reset everything
        await self.reset_everything()

        # Ensure a default app admin user exists
        stmt = select(User).where(User.email == "admin@example.com")
        admin_user = (await self.db.execute(stmt)).scalar_one_or_none()
        if not admin_user:
            admin_user = await self.user_service.register(
                UserCreate(
                    email="admin@example.com",
                    password="admin123",
                    full_name="App Admin",
                )
            )
            admin_user.role = UserRole.ADMIN.value
            self.db.add(admin_user)
            await self.db.flush()

        tenants_info = [
            {"name": "Tenant A", "slug": "tenant-a"},
            {"name": "Tenant B", "slug": "tenant-b"},
        ]

        roles_list = [
            {"name": "owner", "role": OrgRole.OWNER},
            {"name": "admin", "role": OrgRole.ADMIN},
            {"name": "member", "role": OrgRole.MEMBER},
            {"name": "viewer", "role": OrgRole.VIEWER},
        ]

        # Seed data registry for output report
        seeded_tenants = {}
        users_by_tenant = {}

        # 1. Create Tenants and Users
        for t_info in tenants_info:
            # Create Organization
            org = Organization(
                name=t_info["name"],
                slug=t_info["slug"],
                created_by_user_id=admin_user.id,
            )
            self.db.add(org)
            await self.db.flush()
            
            org_id = org.id
            seeded_tenants[t_info["name"]] = str(org_id)
            users_by_tenant[t_info["name"]] = {}

            # Create tenant users for each role
            for r_info in roles_list:
                email = f"{r_info['name']}@{t_info['slug']}.com"
                password = "password123"
                
                # Check if user already exists (could be pre-seeded)
                stmt = select(User).where(User.email == email)
                existing = (await self.db.execute(stmt)).scalar_one_or_none()
                
                if not existing:
                    user = await self.user_service.register(
                        UserCreate(
                            email=email,
                            password=password,
                            full_name=f"{t_info['name']} {r_info['name'].capitalize()}",
                        )
                    )
                else:
                    user = existing
                
                # Create org membership
                member = OrganizationMember(
                    organization_id=org_id,
                    user_id=user.id,
                    role=r_info["role"].value,
                )
                self.db.add(member)
                await self.db.flush()
                
                users_by_tenant[t_info["name"]][r_info["name"]] = {
                    "id": str(user.id),
                    "email": email,
                    "password": password,
                }

        await self.db.commit()

        # Initialize Ingestion Service
        embedder = EmbeddingService(settings=settings.rag)
        vector_store = QdrantVectorStore(settings=settings.rag, embedding_service=embedder)
        processor = app_settings = settings.rag
        from app.services.rag.documents import DocumentProcessor
        doc_processor = DocumentProcessor(settings=processor)
        ingest_svc = IngestionService(processor=doc_processor, vector_store=vector_store)

        # 2. Mock Documents list definitions
        mock_docs = [
            # Finance
            {
                "filename": "quarterly_report.txt",
                "content": "Quarterly Finance Report (Q3 2025)\nRevenue: $125,000\nExpenses: $82,500\nNet Profit: $42,500\nConfidentiality: HIGH. Intended for admin-only access.",
                "area": "finance",
                "confidentiality": "high",
                "permissions": "admin-only",
                "uploader_role": "owner"
            },
            {
                "filename": "budget_forecast.txt",
                "content": "Annual Budget Plan for FY26\nAllocations: Engineering: $500K, HR: $100K, Marketing: $200K\nConfidentiality: MEDIUM. Intended for members.",
                "area": "finance",
                "confidentiality": "medium",
                "permissions": "member",
                "uploader_role": "admin"
            },
            {
                "filename": "payroll_summary.txt",
                "content": "Payroll Distribution Record\nTotal salaries distributed: $65,000 for 12 employees\nConfidentiality: HIGH. Intended for admin-only access.",
                "area": "finance",
                "confidentiality": "high",
                "permissions": "admin-only",
                "uploader_role": "owner"
            },
            {
                "filename": "invoice_summary.txt",
                "content": "Invoice Registry\nPending invoices from vendor Acma Corp: $4,500\nConfidentiality: LOW. Public/viewer read.",
                "area": "finance",
                "confidentiality": "low",
                "permissions": "viewer",
                "uploader_role": "member"
            },
            # HR
            {
                "filename": "employee_handbook.txt",
                "content": "Welcome to the Company Handbook. Working hours are 9am to 5pm, Monday to Friday. Standard leaves: 15 annual days.\nConfidentiality: LOW. Public/viewer read.",
                "area": "hr",
                "confidentiality": "low",
                "permissions": "public",
                "uploader_role": "admin"
            },
            {
                "filename": "leave_policy.txt",
                "content": "Maternity leave: 12 weeks paid. Sick leave: up to 10 days per calendar year. Apply via HR portal.\nConfidentiality: LOW. Public/viewer read.",
                "area": "hr",
                "confidentiality": "low",
                "permissions": "viewer",
                "uploader_role": "member"
            },
            {
                "filename": "hiring_guide.txt",
                "content": "Hiring Procedure: 1. Resume Screen, 2. Technical Interview, 3. Culture Fit, 4. Offer Letter.\nConfidentiality: LOW. Member access.",
                "area": "hr",
                "confidentiality": "low",
                "permissions": "member",
                "uploader_role": "admin"
            },
            {
                "filename": "performance_review.txt",
                "content": "Employee Performance Appraisal Guidelines\nRatings from 1 to 5. Promising employees are evaluated annually.\nConfidentiality: MEDIUM. Member access.",
                "area": "hr",
                "confidentiality": "medium",
                "permissions": "member",
                "uploader_role": "owner"
            },
            # Engineering
            {
                "filename": "system_architecture.txt",
                "content": "Microservices Architecture Map\nGateway routes traffic to Auth Service, Chat Service, and Document Processor via internal gRPC.\nConfidentiality: MEDIUM. Member access.",
                "area": "engineering",
                "confidentiality": "medium",
                "permissions": "member",
                "uploader_role": "admin"
            },
            {
                "filename": "api_guide.txt",
                "content": "Developer API documentation\nGet collections: GET /api/v1/rag/collections. Query: POST /api/v1/rag/query.\nConfidentiality: LOW. Viewer read.",
                "area": "engineering",
                "confidentiality": "low",
                "permissions": "viewer",
                "uploader_role": "member"
            },
            {
                "filename": "deployment_manual.txt",
                "content": "Production Deployment Steps\n1. Build docker images, 2. Run migrations, 3. Boot containers using docker-compose.\nConfidentiality: MEDIUM. Member access.",
                "area": "engineering",
                "confidentiality": "medium",
                "permissions": "member",
                "uploader_role": "admin"
            },
            {
                "filename": "coding_standards.txt",
                "content": "Python Coding Standards\nUse PEP8 conventions. Run Ruff format and lint checks before pushing code.\nConfidentiality: LOW. Public read.",
                "area": "engineering",
                "confidentiality": "low",
                "permissions": "public",
                "uploader_role": "member"
            },
            # Legal
            {
                "filename": "nda_template.txt",
                "content": "Mutual Non-Disclosure Agreement\nBoth parties agree to protect proprietary information and not disclose it to third parties.\nConfidentiality: MEDIUM. Member access.",
                "area": "legal",
                "confidentiality": "medium",
                "permissions": "member",
                "uploader_role": "admin"
            },
            {
                "filename": "client_contract.txt",
                "content": "Enterprise Service Level Agreement\nUptime commitment: 99.9%. Penalty for breach: 10% billing credit.\nConfidentiality: HIGH. Intended for admin-only access.",
                "area": "legal",
                "confidentiality": "high",
                "permissions": "admin-only",
                "uploader_role": "owner"
            },
            {
                "filename": "privacy_policy.txt",
                "content": "Privacy Policy Statement\nWe collect email address and active organization context. We do not sell user data.\nConfidentiality: LOW. Public read.",
                "area": "legal",
                "confidentiality": "low",
                "permissions": "public",
                "uploader_role": "member"
            },
            {
                "filename": "terms_of_service.txt",
                "content": "Terms of Service Agreement\nUsage restrictions: no scraping, no reverse engineering, no denial of service attacks.\nConfidentiality: LOW. Public read.",
                "area": "legal",
                "confidentiality": "low",
                "permissions": "public",
                "uploader_role": "admin"
            },
            # Marketing
            {
                "filename": "marketing_plan.txt",
                "content": "Q4 Product Launch Marketing Campaign\nTargeting tech developers via LinkedIn ads and Twitter newsletters.\nConfidentiality: LOW. Viewer access.",
                "area": "marketing",
                "confidentiality": "low",
                "permissions": "viewer",
                "uploader_role": "member"
            },
            {
                "filename": "campaign_report.txt",
                "content": "Summer Referral Campaign Metrics\nSignups increased by 18%. Total customer acquisition cost: $45.\nConfidentiality: LOW. Member access.",
                "area": "marketing",
                "confidentiality": "low",
                "permissions": "member",
                "uploader_role": "member"
            },
            {
                "filename": "brand_guidelines.txt",
                "content": "Brand Visual Identity Manual\nPrimary color: Navy Blue (#0A192F). Typography font family: Inter.\nConfidentiality: LOW. Public read.",
                "area": "marketing",
                "confidentiality": "low",
                "permissions": "public",
                "uploader_role": "admin"
            },
            {
                "filename": "competitor_analysis.txt",
                "content": "Market Competitive Positioning Study\nCompetitor X has higher pricing but faster support response. Focus on our local hosting privacy.\nConfidentiality: MEDIUM. Member access.",
                "area": "marketing",
                "confidentiality": "medium",
                "permissions": "member",
                "uploader_role": "owner"
            }
        ]

        # Ingest docs for each Tenant
        tmp_dir = os.path.join(str(settings.MEDIA_DIR), "_rag_tmp")
        os.makedirs(tmp_dir, exist_ok=True)

        for tenant_name, u_info in users_by_tenant.items():
            tenant_id = seeded_tenants[tenant_name]
            
            for m_doc in mock_docs:
                tenant_prefix = tenant_name.replace(" ", "_")
                filename = f"{tenant_prefix}_{m_doc['filename']}"
                content = f"Tenant: {tenant_name}\n\n{m_doc['content']}"
                
                # Fetch uploader user record corresponding to uploader_role
                uploader = u_info[m_doc["uploader_role"]]
                
                # Save mock file on disk
                tmp_path = os.path.join(tmp_dir, filename)
                with open(tmp_path, "w", encoding="utf-8") as f:
                    f.write(content)
                
                # Create tracking DB record in postgres
                rag_doc = await self.rag_doc_service.create_document(
                    collection_name="documents",
                    filename=filename,
                    filesize=len(content.encode("utf-8")),
                    filetype="txt",
                    storage_path=f"rag/documents/{filename}",
                    organization_id=UUID(tenant_id),
                    owner_id=UUID(uploader["id"]),
                    area=m_doc["area"],
                    language="en",
                    confidentiality=m_doc["confidentiality"],
                    permissions=m_doc["permissions"],
                )
                
                # Perform the ingestion (sync parsing, chunking, embeddings generation and Qdrant index insertion)
                result = await ingest_svc.ingest_file(
                    filepath=Path(tmp_path),
                    collection_name="documents",
                    replace=True,
                    source_path=filename,
                    tenant_id=tenant_id,
                    area=m_doc["area"],
                    owner=uploader["id"],
                    language="en",
                    confidentiality=m_doc["confidentiality"],
                    permissions=m_doc["permissions"],
                )
                
                # Mark ingestion done in postgres
                await self.rag_doc_service.complete_ingestion(
                    doc_id=str(rag_doc.id),
                    vector_document_id=result.document_id,
                )
                
                # Clean up local file
                Path(tmp_path).unlink(missing_ok=True)

        await self.db.commit()
        await vector_store.client.close()

        return {
            "tenants": seeded_tenants,
            "users": users_by_tenant,
        }
