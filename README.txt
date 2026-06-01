TSP PHOTOGRAPHER PORTAL
========================

WHAT IT DOES
------------
A mobile-friendly web app for photographers to:
- Check out available kits (checks out ALL contents automatically)
- View what's in their kit
- Check kits back in
- Report faults on gear

SETUP
-----
1. Copy .env.example to .env and fill in your values
2. pip install -r requirements.txt
3. python app.py  (for local testing)

DEPLOY TO RAILWAY (free hosting)
----------------------------------
1. Go to https://railway.app and sign up
2. New Project > Deploy from GitHub repo
   OR New Project > Deploy from local directory
3. Add environment variables in Railway dashboard:
   - SNIPEIT_URL = https://assets.theschoolphotographer.com.au
   - SNIPEIT_TOKEN = your_api_token
   - SECRET_KEY = any random string
4. Railway will give you a URL like https://tsp-portal.railway.app

CUSTOM DOMAIN (optional)
--------------------------
In Railway settings, add custom domain:
  portal.theschoolphotographer.com.au

PHOTOGRAPHER ACCESS
-------------------
Share the URL with photographers. They log in with their
Snipe-IT username and password.

Note: Password verification currently checks that the username
exists in Snipe-IT. For production, consider adding LDAP or
proper password verification via Snipe-IT's auth endpoint.
