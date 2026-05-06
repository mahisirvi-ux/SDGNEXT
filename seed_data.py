from app.core.database import SessionLocal
from app.models.domain import IDRFunctional, IntegrationTouchpoint, IDRActionLog
from datetime import datetime, timedelta

def seed_realistic_test_data():
    db = SessionLocal()
    try:
        print("🌱 Seeding realistic test data into the database...")

        # --- SCENARIO 1: Payment Webhook (Assigned to Vendor API Team) ---
        tp1 = IntegrationTouchpoint(name="Payment Gateway Webhook")
        db.add(tp1)
        db.commit() # Commit to get the ID
        
        func1 = IDRFunctional(
            touchpoint_id=tp1.id,
            idr_status="Pending",
            pending_with="Vendor API Team",
            module="Payments",
            technical_owner="Rahul",
            open_pointers="Failing SSL Handshake"
        )
        db.add(func1)

        # Add 3 days of historical logs for TP1
        logs1 = [
            IDRActionLog(touchpoint_id=tp1.id, action_type="Update", action_by="Project Manager", 
                         comment="Initial API requirements sent to vendor.", 
                         open_pointer_history="", created_at=datetime.now() - timedelta(days=5)),
            IDRActionLog(touchpoint_id=tp1.id, action_type="Update", action_by="Project Manager", 
                         comment="", 
                         open_pointer_history="Waiting on Webhook URL from Vendor", created_at=datetime.now() - timedelta(days=3)),
            IDRActionLog(touchpoint_id=tp1.id, action_type="Update", action_by="Project Manager", 
                         comment="Emailed vendor support with error logs.", 
                         open_pointer_history="Vendor provided URL but it fails SSL handshake.", created_at=datetime.now() - timedelta(days=1))
        ]
        db.add_all(logs1)


        # --- SCENARIO 2: Active Directory SSO (Assigned to Bank IT Security) ---
        tp2 = IntegrationTouchpoint(name="Active Directory SSO Sync")
        db.add(tp2)
        db.commit()
        
        func2 = IDRFunctional(
            touchpoint_id=tp2.id,
            idr_status="Pending",
            pending_with="Bank IT Security",
            module="Authentication",
            technical_owner="Gautam",
            open_pointers="Missing certificates in SAML"
        )
        db.add(func2)

        # Add 2 days of historical logs for TP2
        logs2 = [
            IDRActionLog(touchpoint_id=tp2.id, action_type="Update", action_by="Project Manager", 
                         comment="Kickoff call completed with InfoSec.", 
                         open_pointer_history="Need Bank's SAML Metadata XML file.", created_at=datetime.now() - timedelta(days=4)),
            IDRActionLog(touchpoint_id=tp2.id, action_type="Update", action_by="Project Manager", 
                         comment="Reviewed XML file with the dev team.", 
                         open_pointer_history="SAML metadata received, but public certificates are missing.", created_at=datetime.now() - timedelta(days=2))
        ]
        db.add_all(logs2)

        db.commit()
        print("✅ Success! Added 2 new Touchpoints, 2 Functional records, and 5 Action Logs.")

    except Exception as e:
        db.rollback()
        print(f"❌ Failed to seed data: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_realistic_test_data()