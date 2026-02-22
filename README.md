# Kinik Thai Loyalty Point System

Internal loyalty point system for Kinik Thai Co., Ltd.
Built with Streamlit + Supabase.

---

## Project Structure

```
membership/
├── app.py                    # Home page
├── pages/
│   ├── 1_Admin.py            # Admin portal
│   └── 2_Customer.py         # Customer portal
├── db/
│   └── schema.sql            # Supabase schema + RPC functions
├── utils/
│   └── supabase_client.py    # Supabase connection helper
├── .streamlit/
│   └── config.toml           # Theme
├── .env.example              # Environment variable template
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Supabase Project

1. Go to [supabase.com](https://supabase.com) and create a new project.
2. Open the **SQL Editor** in your Supabase dashboard.
3. Paste the entire contents of `db/schema.sql` and run it.
4. Verify the tables (`customers`, `invoices`, `point_lots`, `coupons`, `redeems`, `redeem_allocations`) and functions (`expire_lots`, `create_lot_for_invoice`, `redeem_fifo`) are created.

### 2. Get Credentials

From your Supabase project dashboard:
- **SUPABASE_URL**: Settings → API → Project URL
- **SUPABASE_SERVICE_ROLE_KEY**: Settings → API → Service Role (secret)

### 3. Local Development

```bash
# Clone the repo / enter the project directory
cd membership

# Install dependencies
pip install -r requirements.txt

# Create your .env file
cp .env.example .env
# Edit .env and fill in your Supabase credentials

# Run the app
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Streamlit Cloud Deployment

1. Push this repository to GitHub (make sure `.env` is in `.gitignore`).
2. Go to [share.streamlit.io](https://share.streamlit.io) and connect your GitHub repo.
3. Set the **Main file path** to `app.py`.
4. Under **Advanced settings → Secrets**, add:

```toml
SUPABASE_URL = "https://your-project-ref.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"
```

5. Deploy. Streamlit Cloud will install `requirements.txt` automatically.

---

## Business Rules Summary

| Rule | Value |
|------|-------|
| Points per THB | 1 pt per 10 THB |
| Formula | `floor(invoice_amount / 10)` |
| Point expiry | 1 year from invoice date |
| Redemption threshold | 1,000 points |
| Coupon value | 50 THB |
| Coupon expiry | 1 year from issue date |
| FIFO order | earliest `expires_at` → earliest `earned_at` |

---

## LINE OA Integration

Set a Rich Menu button in LINE Official Account Manager with the link:

```
https://your-app.streamlit.app/Customer
```

No webhook required — customers access the portal directly via the link.

---

## Security Notes

- The **Service Role Key** bypasses Row Level Security. Keep it server-side only (Streamlit Cloud Secrets / `.env`). Never commit it to Git.
- All FIFO redemption logic runs inside a PostgreSQL transaction in the `redeem_fifo` RPC function.
- Invoice duplication is prevented by the `invoice_no` primary key constraint.
- Coupon code uniqueness is enforced by a database `UNIQUE` constraint.
