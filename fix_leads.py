import asyncio
from db import postgres as pg_db
import asyncpg

async def main():
    pool = await asyncpg.create_pool("postgresql://aakashvani:devpassword@localhost:5432/aakashvani")
    
    # Find leads that are stuck in 'pending' but have a completed call_log
    rows = await pool.fetch("""
        SELECT c.session_call_id, c.outcome, c.in_progress, l.id as lead_id, l.status as lead_status, l.client_id, l.campaign_id
        FROM call_logs c
        JOIN leads l ON c.lead_id = l.id
        WHERE l.status = 'pending' AND c.in_progress = FALSE AND c.outcome IS NOT NULL AND c.outcome != 'Unanswered'
        ORDER BY c.created_at DESC;
    """)
    
    print(f"Found {len(rows)} leads to fix")
    for row in rows:
        lead_id = row['lead_id']
        client_id = row['client_id']
        campaign_id = row['campaign_id']
        outcome = row['outcome']
        
        # Decide the new status
        terminal_outcomes = {"Not_Interested", "Interested", "DNC", "Wrong_Number"}
        if outcome in terminal_outcomes or outcome == "dnc":
            new_status = "completed"
        elif outcome == "Callback_Requested":
            new_status = "callback_scheduled"
        else:
            new_status = "completed"
            
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Update the lead status
                await conn.execute("""
                    UPDATE leads SET status = $1 WHERE id = $2 AND client_id = $3
                """, new_status, lead_id, client_id)
                
                # Update campaign counters
                await pg_db.increment_campaign_counters(
                    conn,
                    campaign_id,
                    from_status='pending',
                    to_status=new_status,
                )
                
        print(f"Fixed lead {lead_id} -> {new_status}")

if __name__ == "__main__":
    asyncio.run(main())
