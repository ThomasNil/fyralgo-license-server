from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import sqlite3
import os
from datetime import datetime
import secrets
import string

app = FastAPI()

if not os.path.exists('data'):
    os.makedirs('data')

def init_db():
    conn = sqlite3.connect("data/licenses.db")
    c = conn.cursor()
    # Tabell 1: Licensnycklarna
    c.execute('''CREATE TABLE IF NOT EXISTS licenses
                 (license_key TEXT PRIMARY KEY, max_activations INTEGER DEFAULT 2, is_active INTEGER DEFAULT 1)''')
    
    # Tabell 2: De registrerade kontona (Nu med Telemetri!)
    c.execute('''CREATE TABLE IF NOT EXISTS activations
                 (license_key TEXT, account_number INTEGER, broker TEXT, is_real INTEGER, client_name TEXT, ip_address TEXT, last_active TEXT,
                 UNIQUE(license_key, account_number))''')
                 
    # Tabell 3: IB Whitelist (Gräddfilen)
    c.execute('''CREATE TABLE IF NOT EXISTS ib_whitelist
                 (account_number INTEGER PRIMARY KEY, broker TEXT, is_real INTEGER, client_name TEXT, ip_address TEXT, last_active TEXT)''')
                 
    conn.commit()
    conn.close()

init_db()
@app.get("/verify_license")
def verify_license(request: Request, key: str, account: int, broker: str = "", is_real: int = 0, client_name: str = ""):
    ip_address = request.client.host
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # --- NY REGEL: TILLÅT ALLA DEMO-KONTON GRATIS ---
    if is_real == 0:
        return JSONResponse(content={
            "status": "success", 
            "message": "Authorized (Free Demo Account Access)"
        })

    # (Resten av koden under för IB-whitelist och standardlicenser förblir exakt som tidigare...)
    
    conn = sqlite3.connect("data/licenses.db")
    c = conn.cursor()

    # --- SPECIALFALL: IB WHITELIST ---
    if key.upper() in ["IB", "FREE"]:
        c.execute("SELECT account_number FROM ib_whitelist WHERE account_number = ?", (account,))
        if c.fetchone():
            # Uppdatera telemetri för IB-kunden så du ser att de är online
            c.execute('''UPDATE ib_whitelist SET broker = ?, is_real = ?, client_name = ?, ip_address = ?, last_active = ? 
                         WHERE account_number = ?''', (broker, is_real, client_name, ip_address, now, account))
            conn.commit()
            conn.close()
            return JSONResponse(content={"status": "success", "message": "Authorized via IB Whitelist"})
        else:
            conn.close()
            return JSONResponse(content={"status": "error", "message": "Account is not whitelisted for IB access"})

    # --- STANDARD LICENS-SYSTEM ---
    c.execute("SELECT max_activations, is_active FROM licenses WHERE license_key = ?", (key,))
    row = c.fetchone()
    
    if not row:
        conn.close()
        return JSONResponse(content={"status": "error", "message": "Invalid key"})
    
    max_act, is_active = row
    if is_active == 0:
        conn.close()
        return JSONResponse(content={"status": "error", "message": "License is inactive/blocked"})

    # Kolla om detta kontonummer redan är registrerat på nyckeln
    c.execute("SELECT account_number FROM activations WHERE license_key = ? AND account_number = ?", (key, account))
    if c.fetchone():
        # Kontot fanns! Vi uppdaterar bara telemetrin (sätter en ny 'last_active' etc)
        c.execute('''UPDATE activations SET broker = ?, is_real = ?, client_name = ?, ip_address = ?, last_active = ? 
                     WHERE license_key = ? AND account_number = ?''', 
                  (broker, is_real, client_name, ip_address, now, key, account))
        conn.commit()
        conn.close()
        return JSONResponse(content={"status": "success", "message": "Authorized (Account already registered)"})
        
    # Om det är ett nytt konto, kolla om det finns lediga platser
    c.execute("SELECT COUNT(*) FROM activations WHERE license_key = ?", (key,))
    current_act = c.fetchone()[0]
    
    if current_act >= max_act:
        conn.close()
        return JSONResponse(content={"status": "error", "message": f"Max activations ({max_act}) reached for this key"})
        
    # Det finns plats! Registrera det nya kontot och all dess data
    c.execute('''INSERT INTO activations (license_key, account_number, broker, is_real, client_name, ip_address, last_active) 
                 VALUES (?, ?, ?, ?, ?, ?, ?)''', (key, account, broker, is_real, client_name, ip_address, now))
    conn.commit()
    conn.close()
    
    return JSONResponse(content={"status": "success", "message": f"Authorized and locked to slot {current_act + 1} of {max_act}"})

# --- ADMIN FUNKTIONER ---

ADMIN_SECRET = os.environ["ADMIN_SECRET"]

@app.get("/admin/add_key")
def add_key(secret: str, new_key: str = None, max_act: int = 2):
    if secret != ADMIN_SECRET:
        return {"error": "Unauthorized"}
        
    # Om du inte skickade med en 'new_key' i URL:en, slumpa fram en!
    final_key = new_key if new_key else make_random_key()
        
    conn = sqlite3.connect("data/licenses.db")
    c = conn.cursor()
    try:
        c.execute("INSERT INTO licenses (license_key, max_activations, is_active) VALUES (?, ?, 1)", (final_key, max_act))
        conn.commit()
    except sqlite3.IntegrityError:
        return {"error": "Key already exists, try again"}
    finally: 
        conn.close()
        
    return {"success": f"Key {final_key} created with {max_act} activations."}

@app.get("/admin/whitelist_add")
def whitelist_add(secret: str, account: int):
    if secret != ADMIN_SECRET: return {"error": "Unauthorized"}
    conn = sqlite3.connect("data/licenses.db")
    c = conn.cursor()
    try:
        c.execute("INSERT INTO ib_whitelist (account_number) VALUES (?)", (account,))
        conn.commit()
    except sqlite3.IntegrityError:
        return {"error": "Account already in whitelist"}
    finally: conn.close()
    return {"success": f"Account {account} added to IB whitelist."}

# Hjälpfunktion för att generera nyckel
def make_random_key():
    chars = "".join(c for c in string.ascii_uppercase + string.digits if c not in "IO10")
    parts = ["".join(secrets.choice(chars) for _ in range(4)) for _ in range(3)]
    return f"BPS-{'-'.join(parts)}"
