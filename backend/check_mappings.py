import sqlite3
DB='lifestyle_index.db'
conn=sqlite3.connect(DB)
cur=conn.cursor()
try:
    cur.execute("SELECT email,username,created_at FROM username_mappings ORDER BY created_at DESC")
    rows=cur.fetchall()
    print('mappings_count=', len(rows))
    for r in rows[:50]:
        print(r)
except Exception as e:
    print('ERR', e)
finally:
    conn.close()
