import os
import psycopg2

def fix_db():
    db_url = "postgresql://neondb_owner:npg_UdluByKM74Ss@ep-flat-sky-adpxzlva-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require"
    
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        print("Checking tables...")
        
        # 1. users table
        try:
            cur.execute("ALTER TABLE users ADD COLUMN email_hash TEXT UNIQUE")
            print("Added email_hash to users")
        except Exception as e:
            conn.rollback()
            print(f"Skipped email_hash (might exist): {e}")

        # Ensure email is TEXT (might have been SERIAL or something if id_type was misused)
        # Actually it's probably TEXT NOT NULL.
        
        # 2. valorant_accounts
        missing_acc_cols = [
            ("puuid", "TEXT"),
            ("account_level", "INTEGER DEFAULT 0"),
            ("region", "TEXT DEFAULT 'latam'"),
            ("card_small", "TEXT")
        ]
        for col, col_type in missing_acc_cols:
            try:
                cur.execute(f"ALTER TABLE valorant_accounts ADD COLUMN {col} {col_type}")
                print(f"Added {col} to valorant_accounts")
            except Exception as e:
                conn.rollback()
                print(f"Skipped {col}: {e}")

        # 3. manual_matches
        missing_match_cols = [
            ("result", "TEXT"),
            ("kills", "INTEGER"),
            ("deaths", "INTEGER"),
            ("assists", "INTEGER"),
            ("damage", "INTEGER"),
            ("rounds", "INTEGER"),
            ("acs", "INTEGER"),
            ("kast", "REAL"),
            ("hs", "REAL")
        ]
        for col, col_type in missing_match_cols:
            try:
                cur.execute(f"ALTER TABLE manual_matches ADD COLUMN {col} {col_type}")
                print(f"Added {col} to manual_matches")
            except Exception as e:
                conn.rollback()
                print(f"Skipped {col}: {e}")
        
        conn.commit()
        print("Done!")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    fix_db()
