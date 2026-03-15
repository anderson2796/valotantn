import os
import psycopg2

def check_schema():
    db_url = "postgresql://neondb_owner:npg_UdluByKM74Ss@ep-flat-sky-adpxzlva-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require"
    
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        cur.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'users'
        """)
        columns = cur.fetchall()
        print("Columns in 'users':")
        for col in columns:
            print(f" - {col[0]} ({col[1]})")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    check_schema()
