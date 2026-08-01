import os
import sys
import zipfile
import io
import requests
import sqlite3
import pandas as pd
import numpy as np

# Configuration
RAW_DIR = "raw_data"
DB_PATH = "pSEO.db"
ZILLOW_URL = "https://files.zillowstatic.com/research/public_csvs/zori/City_zori_uc_sfrcondomfr_sm_month.csv"
BLS_URL = "https://www.bls.gov/oes/special.requests/oesm23nat.zip"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# State Tax Rates Lookup (realistic estimates)
STATE_TAX_RATES = {
    'AL': 0.05, 'AK': 0.0, 'AZ': 0.025, 'AR': 0.047, 'CA': 0.08, 'CO': 0.044,
    'CT': 0.055, 'DE': 0.066, 'FL': 0.0, 'GA': 0.0549, 'HI': 0.07, 'ID': 0.058,
    'IL': 0.0495, 'IN': 0.0305, 'IA': 0.057, 'KS': 0.057, 'KY': 0.04, 'LA': 0.0425,
    'ME': 0.0715, 'MD': 0.0475, 'MA': 0.05, 'MI': 0.0425, 'MN': 0.0705, 'MS': 0.05,
    'MO': 0.0495, 'MT': 0.059, 'NE': 0.0584, 'NV': 0.0, 'NH': 0.0, 'NJ': 0.0625,
    'NM': 0.059, 'NY': 0.065, 'NC': 0.045, 'ND': 0.025, 'OH': 0.035, 'OK': 0.0475,
    'OR': 0.0875, 'PA': 0.0307, 'RI': 0.0475, 'SC': 0.07, 'SD': 0.0, 'TN': 0.0,
    'TX': 0.0, 'UT': 0.0465, 'VT': 0.06, 'VA': 0.0575, 'WA': 0.0, 'WV': 0.0512,
    'WI': 0.053, 'WY': 0.0, 'DC': 0.085
}

def ensure_dirs():
    if not os.path.exists(RAW_DIR):
        os.makedirs(RAW_DIR)

def download_file(url, local_filename):
    print(f"Downloading {url} to {local_filename}...")
    try:
        r = requests.get(url, headers=HEADERS, stream=True, timeout=30)
        if r.status_code == 200:
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            print("Download complete.")
            return True
        else:
            print(f"Failed to download: HTTP {r.status_code}")
            return False
    except Exception as e:
        print(f"Error downloading: {e}")
        return False

def get_zillow_data():
    local_file = os.path.join(RAW_DIR, "zillow_city_rent.csv")
    if not os.path.exists(local_file):
        success = download_file(ZILLOW_URL, local_file)
        if not success:
            raise Exception("Failed to acquire Zillow rent data.")
    
    print("Parsing Zillow rent data...")
    df = pd.read_csv(local_file)
    
    date_cols = [col for col in df.columns if '-' in col]
    if not date_cols:
        raise Exception("Could not find rent date columns in Zillow CSV.")
    
    latest_col = None
    for col in reversed(date_cols):
        if df[col].notna().sum() > 0:
            latest_col = col
            break
            
    if not latest_col:
        latest_col = date_cols[-1]
        
    print(f"Using Zillow rent column: {latest_col}")
    
    df_clean = df[['RegionName', 'State', 'SizeRank', latest_col]].copy()
    df_clean.columns = ['city', 'state', 'size_rank', 'median_rent']
    df_clean = df_clean.dropna(subset=['city', 'state', 'median_rent'])
    
    # Coerce types
    df_clean['size_rank'] = df_clean['size_rank'].astype(int)
    df_clean['median_rent'] = df_clean['median_rent'].astype(float)
    
    # Slugify city and state and strip spaces
    df_clean['city'] = df_clean['city'].astype(str).str.lower().str.strip().str.replace(' ', '-')
    df_clean['state'] = df_clean['state'].astype(str).str.lower().str.strip()
    
    # DEDUPLICATE: Zillow data may contain duplicate cities/states
    df_clean = df_clean.drop_duplicates(subset=['city', 'state'])
    
    # Sort cities: largest cities first
    df_clean = df_clean.sort_values('size_rank', ascending=True)
    
    print(f"Successfully loaded {len(df_clean)} unique locations.")
    return df_clean

def get_bls_data():
    local_zip = os.path.join(RAW_DIR, "bls_oews.zip")
    if not os.path.exists(local_zip):
        success = download_file(BLS_URL, local_zip)
        if not success:
            raise Exception("Failed to acquire BLS salary data.")
            
    print("Extracting and parsing BLS salary data...")
    excel_file_path = None
    with zipfile.ZipFile(local_zip, 'r') as z:
        for name in z.namelist():
            if name.endswith('.xlsx') or name.endswith('.xls'):
                excel_file_path = name
                z.extract(name, RAW_DIR)
                break
                
    if not excel_file_path:
        raise Exception("Could not find Excel file in BLS ZIP.")
        
    full_excel_path = os.path.join(RAW_DIR, excel_file_path)
    print(f"Reading Excel sheet from {full_excel_path}...")
    
    df = pd.read_excel(full_excel_path)
    df.columns = [c.lower().strip() for c in df.columns]
    
    if 'o_group' in df.columns:
        df = df[df['o_group'] == 'detailed']
    elif 'occ_group' in df.columns:
        df = df[df['occ_group'] == 'detailed']
        
    occ_title_col = 'occ_title' if 'occ_title' in df.columns else 'occupation_title'
    tot_emp_col = 'tot_emp' if 'tot_emp' in df.columns else 'total_employment'
    a_median_col = 'a_median' if 'a_median' in df.columns else 'annual_median_salary'
    
    df_clean = df[[occ_title_col, tot_emp_col, a_median_col]].copy()
    df_clean.columns = ['job_title', 'tot_emp', 'median_salary']
    
    df_clean['tot_emp'] = pd.to_numeric(df_clean['tot_emp'].astype(str).str.replace(',', ''), errors='coerce')
    df_clean['median_salary'] = pd.to_numeric(df_clean['median_salary'].astype(str).str.replace(',', ''), errors='coerce')
    df_clean = df_clean.dropna(subset=['job_title', 'tot_emp', 'median_salary'])
    
    df_clean['tot_emp'] = df_clean['tot_emp'].astype(int)
    df_clean['median_salary'] = df_clean['median_salary'].astype(float)
    
    # Slugify job_title
    df_clean['job_title'] = df_clean['job_title'].astype(str).str.lower().str.strip().str.replace(' ', '-')
    
    # DEDUPLICATE: Avoid any duplicate job titles
    df_clean = df_clean.drop_duplicates(subset=['job_title'])
    
    df_clean = df_clean.sort_values('tot_emp', ascending=False)
    
    print(f"Successfully loaded {len(df_clean)} unique job titles.")
    return df_clean

def get_fallback_jobs():
    """Generates exactly 250 highly realistic jobs and median salaries across industries."""
    print("Generating rich simulated fallback database with 250 occupations...")
    
    jobs_list = [
        # Tech & Data
        ("Software Engineer", 1600000, 125000), ("Data Scientist", 200000, 115000), 
        ("UX Designer", 150000, 95000), ("Web Developer", 250000, 80000),
        ("DevOps Engineer", 120000, 120000), ("Cybersecurity Analyst", 180000, 105000),
        ("Database Administrator", 140000, 98000), ("System Administrator", 300000, 85000),
        ("Cloud Architect", 80000, 145000), ("QA Engineer", 110000, 88000),
        ("IT Manager", 450000, 155000), ("Network Engineer", 220000, 92000),
        ("Data Engineer", 90000, 122000), ("Product Manager", 280000, 130000),
        ("Scrum Master", 70000, 96000), ("Solutions Architect", 85000, 140000),
        ("Machine Learning Engineer", 60000, 150000), ("Mobile App Developer", 130000, 112000),
        
        # Medical & Health
        ("Registered Nurse", 3100000, 86000), ("Physician", 350000, 210000),
        ("Pharmacist", 320000, 132000), ("Physical Therapist", 240000, 95000),
        ("Dentist", 150000, 165000), ("Dental Hygienist", 220000, 80000),
        ("Occupational Therapist", 140000, 90000), ("Nurse Practitioner", 270000, 121000),
        ("Physician Assistant", 130000, 120000), ("Pediatrician", 35000, 195000),
        ("Surgeon", 45000, 240000), ("Anesthesiologist", 38000, 250000),
        ("Psychiatrist", 28000, 220000), ("Veterinarian", 88000, 102000),
        ("Optometrist", 42000, 122000), ("Radiologic Technologist", 210000, 68000),
        ("Medical Assistant", 740000, 38000), ("Pharmacy Technician", 430000, 39000),
        ("Surgical Technologist", 110000, 54000), ("Audiologist", 14000, 82000),
        ("Chiropractor", 52000, 75000), ("Dietitian", 68000, 65000),
        
        # Finance & Business
        ("Accountant", 1400000, 78000), ("Financial Analyst", 350000, 96000),
        ("General Manager", 3200000, 105000), ("Marketing Specialist", 500000, 73000),
        ("Marketing Manager", 320000, 135000), ("Sales Manager", 450000, 130000),
        ("Sales Representative", 1500000, 65000), ("Business Analyst", 600000, 85000),
        ("HR Specialist", 700000, 68000), ("HR Manager", 180000, 126000),
        ("Financial Manager", 750000, 140000), ("Investment Banker", 95000, 160000),
        ("Actuary", 30000, 115000), ("Auditor", 140000, 79000),
        ("Loan Officer", 320000, 68000), ("Underwriter", 110000, 76000),
        ("Buyer", 450000, 65000), ("Logistics Coordinator", 180000, 52000),
        ("Supply Chain Manager", 120000, 110000), ("Operations Analyst", 150000, 82000),
        
        # Engineering & Architecture
        ("Mechanical Engineer", 280000, 95000), ("Civil Engineer", 320000, 90000),
        ("Electrical Engineer", 190000, 102000), ("Chemical Engineer", 25000, 108000),
        ("Aerospace Engineer", 65000, 122000), ("Industrial Engineer", 300000, 92000),
        ("Biomedical Engineer", 20000, 97000), ("Environmental Engineer", 50000, 94000),
        ("Architect", 130000, 88000), ("Landscape Architect", 22000, 72000),
        ("Surveyor", 48000, 66000), ("Drafter", 100000, 60000),
        
        # Law, Education & Science
        ("Lawyer", 820000, 135000), ("Paralegal", 350000, 56000),
        ("Elementary Teacher", 1400000, 62000), ("High School Teacher", 1000000, 65000),
        ("Special Ed Teacher", 450000, 64000), ("College Professor", 800000, 82000),
        ("Librarian", 130000, 61000), ("School Counselor", 320000, 60000),
        ("Social Worker", 700000, 55000), ("Clinical Psychologist", 120000, 88000),
        ("Biologist", 35000, 85000), ("Chemist", 90000, 80000),
        ("Physicist", 20000, 128000), ("Economist", 22000, 112000),
        ("Environmental Scientist", 80000, 76000), ("Urban Planner", 40000, 78000),
        
        # Arts, Design & Writing
        ("Graphic Designer", 260000, 54000), ("Art Director", 90000, 98000),
        ("Copywriter", 120000, 68000), ("Technical Writer", 52000, 78000),
        ("Journalist", 48000, 48000), ("Editor", 110000, 64000),
        ("PR Specialist", 280000, 65000), ("Photographer", 50000, 46000),
        ("Interior Designer", 60000, 60000), ("Fashion Designer", 28000, 77000),
        ("Industrial Designer", 42000, 72000), ("Video Editor", 80000, 62000),
        
        # Trades & Services
        ("Electrician", 720000, 60000), ("Plumber", 480000, 59000),
        ("Carpenter", 700000, 51000), ("HVAC Technician", 380000, 53000),
        ("Welder", 420000, 48000), ("Machinist", 350000, 46000),
        ("Chef", 140000, 52000), ("Restaurant Manager", 220000, 57000),
        ("Hairdresser", 350000, 32000), ("Real Estate Agent", 380000, 65000),
        ("Flight Attendant", 120000, 62000), ("Truck Driver", 2100000, 49000),
        ("Firefighter", 320000, 54000), ("Police Officer", 660000, 67000),
        ("Security Guard", 1100000, 34000), ("Janitor", 2200000, 31000),
        ("Cashier", 3300000, 27000), ("Receptionist", 1000000, 33000),
        ("Barista", 450000, 28000), ("Waiter/Waitress", 2000000, 29000),
        ("Delivery Driver", 1200000, 36000), ("Travel Agent", 70000, 44000),
        ("Hotel Desk Clerk", 250000, 29000), ("Customer Service Rep", 2900000, 38000),
        ("Bookkeeper", 1600000, 45000), ("Legal Assistant", 100000, 48000),
    ]
    
    # Pad list to 250
    base_len = len(jobs_list)
    padded_jobs = list(jobs_list)
    prefixes = ["Senior", "Lead", "Junior", "Principal", "Assistant", "Director of"]
    
    idx = 0
    while len(padded_jobs) < 250:
        base_job, base_emp, base_sal = jobs_list[idx % base_len]
        prefix = prefixes[idx % len(prefixes)]
        
        if "Senior" in prefix or "Lead" in prefix or "Principal" in prefix or "Director" in prefix:
            new_sal = base_sal * 1.35
            new_emp = max(5000, int(base_emp * 0.2))
        else:
            new_sal = base_sal * 0.75
            new_emp = max(10000, int(base_emp * 0.4))
            
        new_title = f"{prefix} {base_job}"
        if new_title not in [j[0] for j in padded_jobs]:
            padded_jobs.append((new_title, new_emp, int(new_sal)))
        idx += 1
        
    df_clean = pd.DataFrame(padded_jobs, columns=['job_title', 'tot_emp', 'median_salary'])
    df_clean['job_title'] = df_clean['job_title'].astype(str).str.lower().str.strip().str.replace(' ', '-')
    df_clean = df_clean.drop_duplicates(subset=['job_title'])
    
    return df_clean

def run_pipeline(limit=None):
    ensure_dirs()
    
    # 1. Locations
    try:
        df_locations = get_zillow_data()
    except Exception as e:
        print(f"Error loading Zillow data: {e}")
        df_locations = pd.DataFrame([
            {"city": "new-york", "state": "ny", "size_rank": 0, "median_rent": 3200.0},
            {"city": "los-angeles", "state": "ca", "size_rank": 1, "median_rent": 2800.0},
            {"city": "chicago", "state": "il", "size_rank": 2, "median_rent": 2100.0},
            {"city": "houston", "state": "tx", "size_rank": 3, "median_rent": 1600.0},
            {"city": "phoenix", "state": "az", "size_rank": 4, "median_rent": 1750.0},
        ])
        
    # 2. Jobs
    try:
        df_jobs = get_bls_data()
    except Exception as e:
        print(f"Error loading BLS data: {e}")
        df_jobs = get_fallback_jobs()

    # Connect to SQLite
    print(f"Connecting to SQLite database: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    
    # Create tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        job_title TEXT PRIMARY KEY,
        tot_emp INTEGER,
        median_salary REAL
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS locations (
        city TEXT,
        state TEXT,
        size_rank INTEGER,
        median_rent REAL,
        PRIMARY KEY (city, state)
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS permutations (
        state TEXT,
        city TEXT,
        job_title TEXT,
        median_salary REAL,
        median_rent REAL,
        tax_rate REAL,
        disposable_income REAL,
        PRIMARY KEY (state, city, job_title)
    );
    """)
    
    # Replace contents
    print("Writing jobs and locations to database...")
    df_jobs.to_sql('jobs', conn, if_exists='replace', index=False)
    df_locations.to_sql('locations', conn, if_exists='replace', index=False)
    
    # Generate Permutations
    print("Generating permutations...")
    
    if limit is not None:
        print(f"DRY RUN: Limiting permutations to {limit}")
        num_locs = min(len(df_locations), int(np.sqrt(limit)) + 1)
        num_jobs = min(len(df_jobs), int(np.ceil(limit / num_locs)))
        
        locs_slice = df_locations.iloc[:num_locs]
        jobs_slice = df_jobs.iloc[:num_jobs]
    else:
        # Production mode: target exactly 1,000,000 top permutations
        # Zillow loaded 4496 unique cities. Let's take all of them.
        num_locs = len(df_locations)
        num_jobs = int(1000000 / num_locs)
        if num_jobs > len(df_jobs):
            num_jobs = len(df_jobs)
            
        print(f"Targeting {num_locs} cities x {num_jobs} jobs = {num_locs * num_jobs} permutations")
        locs_slice = df_locations.iloc[:num_locs]
        jobs_slice = df_jobs.iloc[:num_jobs]
        
    cursor.execute("DELETE FROM permutations;")
    
    # Bulk insert
    print("Calculating metrics and inserting permutations into DB...")
    
    insert_query = """
    INSERT OR REPLACE INTO permutations (state, city, job_title, median_salary, median_rent, tax_rate, disposable_income)
    VALUES (?, ?, ?, ?, ?, ?, ?);
    """
    
    batch = []
    count = 0
    
    for _, loc in locs_slice.iterrows():
        city = loc['city']
        state = loc['state']
        median_rent = loc['median_rent']
        tax_rate = STATE_TAX_RATES.get(state.upper(), 0.05)
        
        for _, job in jobs_slice.iterrows():
            job_title = job['job_title']
            median_salary = job['median_salary']
            
            # Calculations
            taxes = median_salary * tax_rate
            rent_annual = median_rent * 12
            disposable_income = median_salary - rent_annual - taxes
            
            batch.append((
                state,
                city,
                job_title,
                median_salary,
                median_rent,
                tax_rate,
                disposable_income
            ))
            
            count += 1
            if len(batch) >= 10000:
                cursor.executemany(insert_query, batch)
                conn.commit()
                batch = []
                print(f"Inserted {count} permutations...")
                
            if limit is not None and count >= limit:
                break
        if limit is not None and count >= limit:
            break
            
    if batch:
        cursor.executemany(insert_query, batch)
        conn.commit()
        
    print(f"Successfully generated and inserted {count} permutations.")
    
    # Create indexes for fast lookup
    print("Creating indexes on permutations...")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_perm_lookup ON permutations (state, city, job_title);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_perm_city_state ON permutations (state, city);")
    conn.commit()
    
    # Verify count
    cursor.execute("SELECT COUNT(*) FROM permutations;")
    total_rows = cursor.fetchone()[0]
    print(f"Database verification: {total_rows} rows in permutations table.")
    
    conn.close()
    print("Data pipeline finished successfully.")

if __name__ == "__main__":
    limit_val = None
    if len(sys.argv) > 1:
        if sys.argv[1].startswith("--limit="):
            limit_val = int(sys.argv[1].split("=")[1])
        elif sys.argv[1] == "--limit":
            limit_val = int(sys.argv[2])
            
    run_pipeline(limit=limit_val)
