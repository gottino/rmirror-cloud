#!/bin/bash
set -e

# Setup PostgreSQL for rMirror Cloud
# This script creates the database, user, and runs migrations

# Configuration
DB_NAME="rmirror"
DB_USER="rmirror"
DB_PASSWORD="${POSTGRES_PASSWORD:-$(openssl rand -base64 32)}"

echo "Setting up PostgreSQL for rMirror Cloud..."
echo "Database: $DB_NAME"
echo "User: $DB_USER"
echo ""

# Create database and user
sudo -u postgres psql <<EOF
-- Create user if not exists
DO \$\$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_user WHERE usename = '$DB_USER') THEN
      CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';
   END IF;
END
\$\$;

-- Create database if not exists
SELECT 'CREATE DATABASE $DB_NAME OWNER $DB_USER'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DB_NAME')\gexec

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;

\c $DB_NAME

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO $DB_USER;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO $DB_USER;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO $DB_USER;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $DB_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $DB_USER;

EOF

echo ""
echo "✓ PostgreSQL database and user created successfully"
echo ""
echo "Connection details:"
echo "  Host: localhost"
echo "  Port: 5432"
echo "  Database: $DB_NAME"
echo "  User: $DB_USER"
echo "  Password: $DB_PASSWORD"
echo ""
echo "Connection URL:"
echo "  postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME"
echo ""
echo "Add this to your .env file:"
echo "  DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME"
echo ""
