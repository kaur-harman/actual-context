import os
import json
import psycopg2
import psycopg2.pool
from dotenv import load_dotenv
 
load_dotenv()
 
_pool = None
 
def get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1, maxconn=5,
            host=os.getenv("ALLOYDB_HOST"),
            port=int(os.getenv("ALLOYDB_PORT", 5432)),
            dbname=os.getenv("ALLOYDB_DB", "postgres"),
            user=os.getenv("ALLOYDB_USER", "postgres"),
            password=os.getenv("ALLOYDB_PASSWORD"),
            connect_timeout=10
        )
    return _pool
 
def get_conn():
    return get_pool().getconn()
 
def release_conn(conn):
    get_pool().putconn(conn)
 
def save_user_profile(profile: dict) -> str:
    """Insert or update user profile with AlloyDB embedding."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        profile_text = (
            f"Age {profile.get('age')}, {profile.get('city')}, "
            f"{profile.get('sector')} sector, income {profile.get('income_lpa')} LPA, "
            f"home loan {json.dumps(profile.get('home_loan', {}))}, "
            f"investments {json.dumps(profile.get('investments', {}))}, "
            f"{profile.get('dependents')} dependents, "
            f"travel plans: {profile.get('travel_plans', 'none')}"
        )
        cur.execute("""
            INSERT INTO user_profiles
              (name, age, city, income_lpa, sector, home_loan,
               investments, dependents, travel_plans, profile_text, profile_vector)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    embedding('text-embedding-005', %s)::vector)
            RETURNING user_id
        """, (
            profile.get("name"), profile.get("age"), profile.get("city"),
            profile.get("income_lpa"), profile.get("sector"),
            json.dumps(profile.get("home_loan", {})),
            json.dumps(profile.get("investments", {})),
            profile.get("dependents"), profile.get("travel_plans"),
            profile_text, profile_text
        ))
        user_id = str(cur.fetchone()[0])
        conn.commit()
        return user_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        release_conn(conn)
 
def save_news_event(event: dict) -> str:
    """Store a validated news event with embedding."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        embed_text = f"{event.get('headline')} {event.get('summary', '')}"
        cur.execute("""
            INSERT INTO news_events
              (headline, source_url, validated, causal_chain,
               affected_sectors, event_vector)
            VALUES (%s,%s,%s,%s,%s,
                    embedding('text-embedding-005', %s)::vector)
            RETURNING event_id
        """, (
            event.get("headline"), event.get("source_url", ""),
            event.get("validated", False),
            json.dumps(event.get("causal_chain", {})),
            event.get("affected_sectors", []),
            embed_text
        ))
        event_id = str(cur.fetchone()[0])
        conn.commit()
        return event_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        release_conn(conn)
 
def save_impact_log(user_id: str, event_id: str, impact: dict) -> str:
    """Save the personal impact translation result."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO impact_logs
              (user_id, event_id, impact_summary, reasoning_chain, flagged)
            VALUES (%s,%s,%s,%s,%s)
            RETURNING impact_id
        """, (
            user_id, event_id,
            impact.get("summary", ""),
            json.dumps(impact.get("reasoning_chain", {})),
            impact.get("flagged", False)
        ))
        impact_id = str(cur.fetchone()[0])
        conn.commit()
        return impact_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        release_conn(conn)
 
def get_user_profile(user_id: str) -> dict:
    """Fetch a user profile by ID."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, name, age, city, income_lpa, sector,
                   home_loan, investments, dependents, travel_plans
            FROM user_profiles WHERE user_id = %s
        """, (user_id,))
        row = cur.fetchone()
        if not row:
            return {}
        cols = ["user_id","name","age","city","income_lpa","sector",
                "home_loan","investments","dependents","travel_plans"]
        return dict(zip(cols, row))
    finally:
        release_conn(conn)
 
def check_flagged_events(user_id: str, new_headline: str) -> list:
    """Use AlloyDB ai.if() to semantically match new news to flagged events."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT fe.flag_id, ne.headline, fe.flag_reason
            FROM flagged_events fe
            JOIN news_events ne ON fe.event_id = ne.event_id
            WHERE fe.user_id = %s AND fe.resolved = FALSE
              AND ai.if(
                prompt => 'Is the new article: "' || %s ||
                          '" a development related to: "' || ne.headline ||
                          '"? Answer yes or no only.',
                model_id => 'gemini-2.5-flash'
              )
        """, (user_id, new_headline))
        rows = cur.fetchall()
        return [{"flag_id": str(r[0]), "original_headline": r[1],
                 "flag_reason": r[2]} for r in rows]
    except Exception:
        return []
    finally:
        release_conn(conn)
