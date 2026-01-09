# Privacy Policy

**Effective Date:** January 9, 2026
**Last Updated:** January 9, 2026

## 1. Introduction

rMirror Cloud ("we," "our," or "us") is committed to protecting your privacy and personal data. This Privacy Policy explains how we collect, use, disclose, and safeguard your information when you use our service for reMarkable tablet notebook synchronization and transcription.

**Data Controller:**
rMirror Cloud
Switzerland
Email: support@rmirror.io

This Privacy Policy complies with:
- Swiss Federal Act on Data Protection (FADP/revFADP, effective September 1, 2023)
- EU General Data Protection Regulation (GDPR) where applicable
- Swiss-US Data Privacy Framework

## 2. Information We Collect

### 2.1 Account Information
When you create an account, we collect:
- Email address
- Name
- Authentication credentials (managed by Clerk Inc.)
- Account creation date
- Subscription tier and billing status

### 2.2 Notebook Content
When you sync notebooks from your reMarkable tablet:
- Handwritten notes (binary .rm files)
- Notebook metadata (titles, creation dates, modification dates, folder structure)
- Generated PDFs of your notebook pages
- OCR-transcribed text from your handwritten notes

### 2.3 Usage Data
- Quota usage (OCR pages processed)
- Sync history and timestamps
- API access logs
- Error reports and debugging information

### 2.4 Integration Data
If you connect third-party integrations:
- Integration service credentials (encrypted)
- Sync preferences and settings
- External service identifiers (e.g., Notion database IDs)

### 2.5 Technical Data
- IP address
- Browser type and version
- Operating system
- Device information
- Access times and dates

## 3. How We Use Your Information

We process your personal data for the following purposes:

### 3.1 Service Delivery (Contractual Necessity)
- Synchronizing your reMarkable notebooks to the cloud
- Performing OCR transcription of your handwritten notes
- Generating searchable PDFs
- Managing your account and subscription
- Syncing to connected integrations (Notion, etc.)

### 3.2 Communication (Contractual Necessity & Legitimate Interest)
- Sending service notifications (quota warnings, sync status)
- Responding to support inquiries
- Sending critical security updates

### 3.3 Service Improvement (Legitimate Interest)
- Analyzing usage patterns to improve service performance
- Debugging technical issues
- Monitoring service health and reliability

### 3.4 Legal Compliance (Legal Obligation)
- Complying with applicable laws and regulations
- Responding to lawful requests from authorities
- Protecting our legal rights

## 4. Legal Basis for Processing (GDPR/FADP)

We process your personal data based on:
- **Consent:** When you create an account and agree to our Terms of Service
- **Contract:** To fulfill our service obligations to you
- **Legitimate Interest:** To improve and secure our service
- **Legal Obligation:** To comply with Swiss and EU data protection laws

## 5. Third-Party Service Providers

We use the following third-party processors to deliver our service:

### 5.1 Authentication & Identity Management
**Clerk Inc. (USA)**
- **Purpose:** User authentication, account management
- **Data Shared:** Email address, name, authentication credentials
- **Data Location:** United States
- **Safeguards:** Swiss-US Data Privacy Framework participant; Standard Contractual Clauses (SCCs)
- **Privacy Policy:** https://clerk.com/privacy

### 5.2 OCR Processing
**Anthropic PBC (USA) - Claude API**
- **Purpose:** Optical Character Recognition (handwriting transcription)
- **Data Shared:** PDF images of notebook pages for OCR processing
- **Data Location:** United States
- **Retention:** Anthropic does not retain OCR input data beyond processing time (per their privacy policy)
- **Safeguards:** Swiss-US Data Privacy Framework participant; Standard Contractual Clauses (SCCs)
- **Privacy Policy:** https://www.anthropic.com/privacy

### 5.3 Email Communications
**Resend Inc. (USA)**
- **Purpose:** Transactional email delivery (welcome emails, quota notifications)
- **Data Shared:** Email address, name, service usage data for notifications
- **Data Location:** United States
- **Safeguards:** Swiss-US Data Privacy Framework participant; Standard Contractual Clauses (SCCs)
- **Privacy Policy:** https://resend.com/privacy

### 5.4 Infrastructure Hosting
**Hetzner Online GmbH (Germany)**
- **Purpose:** Server infrastructure, database hosting, file storage
- **Data Shared:** All service data (notebooks, user data, database)
- **Data Location:** European Union (Germany)
- **Safeguards:** EU-based company, GDPR compliant
- **Privacy Policy:** https://www.hetzner.com/rechtliches/datenschutz

### 5.5 Storage (S3-Compatible)
**Hetzner Storage Box OR Backblaze B2 (depending on configuration)**
- **Purpose:** Long-term storage of PDF files
- **Data Shared:** Generated PDF files of notebook pages
- **Data Location:**
  - Hetzner: EU (Germany)
  - Backblaze: USA (if used)
- **Safeguards:** Encrypted at rest; SCCs if Backblaze is used

### 5.6 Payment Processing (Future - Phase 2)
**Stripe Inc. (USA)**
- **Purpose:** Subscription payment processing
- **Data Shared:** Payment information (credit card, billing address)
- **Data Location:** United States
- **Note:** Not yet active (planned for February 2026)
- **Safeguards:** Swiss-US Data Privacy Framework participant; PCI DSS Level 1 certified
- **Privacy Policy:** https://stripe.com/privacy

### 5.7 Optional User-Connected Integrations
**Notion Labs Inc. (USA) - If you enable Notion sync**
- **Purpose:** Syncing notebook content to your Notion workspace
- **Data Shared:** Notebook titles, page content, OCR text, metadata
- **Data Location:** United States (Notion's infrastructure)
- **Control:** You explicitly authorize this connection and can disconnect anytime
- **Privacy Policy:** https://www.notion.so/privacy

**Note:** All third-party processors are bound by Data Processing Agreements (DPAs) requiring compliance with GDPR and Swiss FADP standards.

## 6. International Data Transfers

### 6.1 Transfers to the United States
Your data may be transferred to and processed in the United States by:
- Clerk (authentication)
- Anthropic (OCR processing)
- Resend (email)
- Notion (if you enable integration)
- Stripe (when payment processing launches)

**Safeguards for US Transfers:**
1. **Swiss-US Data Privacy Framework:** Our US service providers participate in this framework, providing adequacy for transfers from Switzerland
2. **Standard Contractual Clauses (SCCs):** We execute SCCs approved by the Swiss FDPIC and EU Commission
3. **Supplementary Measures:** We conduct Transfer Impact Assessments (TIAs) and implement technical safeguards (encryption, access controls)

### 6.2 Transfers within the EU/EEA
Data stored on Hetzner infrastructure remains within Germany (EU), providing adequacy under Swiss and EU law.

### 6.3 Your Rights Regarding International Transfers
You have the right to:
- Object to international data transfers
- Request information about safeguards in place
- Request a copy of applicable SCCs

## 7. Data Retention

We retain your personal data for the following periods:

| Data Type | Retention Period | Justification |
|-----------|------------------|---------------|
| Account Information | Duration of account + 30 days after deletion | Contractual necessity |
| Notebook Content | Duration of account + 30 days after deletion | Service delivery |
| OCR Transcriptions | Duration of account + 30 days after deletion | Service delivery |
| Usage Logs | 90 days | Service improvement, security |
| Email Communications | 2 years | Legal compliance, support |
| Payment Records (future) | 10 years | Swiss tax law compliance |
| Integration Credentials | Until disconnected by user | Service functionality |

After these periods, data is permanently deleted from our systems and backups.

## 8. Data Security

We implement appropriate technical and organizational measures:

### 8.1 Technical Measures
- **Encryption in Transit:** TLS 1.3 for all data transmission
- **Encryption at Rest:** AES-256 encryption for databases and file storage
- **Access Controls:** Role-based access control (RBAC), multi-factor authentication for admin access
- **API Security:** Token-based authentication, rate limiting, input validation
- **Secure Credential Storage:** Integration credentials encrypted with separate encryption keys

### 8.2 Organizational Measures
- Regular security audits and vulnerability assessments
- Employee confidentiality agreements
- Data breach response procedures
- Limited access on need-to-know basis
- Regular security training

### 8.3 Data Breach Notification
In the event of a data breach affecting your personal data, we will:
- Notify you within 72 hours of becoming aware
- Notify the Swiss Federal Data Protection and Information Commissioner (FDPIC) if required
- Provide details of the breach, potential impact, and mitigation measures

## 9. Your Rights Under Swiss FADP and GDPR

You have the following rights regarding your personal data:

### 9.1 Right to Access (Art. 25 FADP, Art. 15 GDPR)
Request confirmation of what personal data we process and obtain a copy.

### 9.2 Right to Rectification (Art. 32 FADP, Art. 16 GDPR)
Request correction of inaccurate or incomplete personal data.

### 9.3 Right to Erasure / Right to be Forgotten (Art. 32 FADP, Art. 17 GDPR)
Request deletion of your personal data when:
- Data no longer necessary for original purpose
- You withdraw consent
- You object to processing and there are no overriding legitimate grounds
- Data was unlawfully processed

### 9.4 Right to Data Portability (Art. 28 FADP, Art. 20 GDPR)
Receive your personal data in a structured, machine-readable format (JSON/CSV).

### 9.5 Right to Restriction of Processing (Art. 32 FADP, Art. 18 GDPR)
Request limitation of processing in certain circumstances.

### 9.6 Right to Object (Art. 30 FADP, Art. 21 GDPR)
Object to processing based on legitimate interests or direct marketing.

### 9.7 Right to Withdraw Consent
Withdraw consent at any time (without affecting prior processing).

### 9.8 Right to Lodge a Complaint
File a complaint with:
- **Switzerland:** Federal Data Protection and Information Commissioner (FDPIC)
  https://www.edoeb.admin.ch/
- **EU:** Your local Data Protection Authority

### 9.9 Exercising Your Rights
To exercise any of these rights, contact us at: support@rmirror.io

We will respond within:
- **30 days** (Swiss FADP standard)
- **1 month** (GDPR standard, extendable to 3 months for complex requests)

## 10. Children's Privacy

rMirror Cloud is not intended for children under 16 years of age. We do not knowingly collect personal data from children. If you believe we have inadvertently collected data from a child, contact us immediately for deletion.

## 11. Cookies and Tracking

### 11.1 Essential Cookies
We use essential cookies for:
- Authentication (Clerk session management)
- Security (CSRF protection)
- Service functionality

### 11.2 No Analytics or Marketing Cookies
We currently do not use analytics, advertising, or non-essential tracking cookies.

### 11.3 Browser Controls
You can control cookies through your browser settings. Blocking essential cookies may impair service functionality.

## 12. Automated Decision-Making

We do not use automated decision-making or profiling that produces legal effects or similarly significant effects on you.

## 13. Changes to This Privacy Policy

We may update this Privacy Policy to reflect:
- Changes in our data practices
- New features or services
- Legal or regulatory requirements

**Notification of Changes:**
- Material changes: Email notification + prominent notice in dashboard
- Non-material changes: Updated "Last Updated" date

## 14. Data Controller Contact Information

**Data Controller:**
rMirror Cloud
Switzerland
Email: support@rmirror.io

**Data Protection Inquiries:**
For questions about your personal data, privacy rights, or this policy:
Email: privacy@rmirror.io

## 15. Supervisory Authority

**Switzerland:**
Federal Data Protection and Information Commissioner (FDPIC)
Feldeggweg 1
3003 Berne
Switzerland
Tel: +41 58 462 43 95
Email: info@edoeb.admin.ch
Website: https://www.edoeb.admin.ch/

**EU (if applicable):**
Contact your local Data Protection Authority
https://edpb.europa.eu/about-edpb/about-edpb/members_en

## 16. Additional Information for EU/EEA Users

If you are located in the EU/EEA, the following additional information applies:

### 16.1 Legal Basis Summary
| Processing Activity | Legal Basis |
|---------------------|-------------|
| Account creation and management | Contract, Consent |
| Notebook sync and OCR | Contract |
| Email notifications | Contract, Legitimate Interest |
| Integration sync (Notion, etc.) | Consent |
| Service improvement | Legitimate Interest |
| Legal compliance | Legal Obligation |

### 16.2 Legitimate Interest Balancing
Where we rely on legitimate interests, we have conducted balancing tests demonstrating our interests do not override your fundamental rights and freedoms.

### 16.3 Representative in the EU
If required under GDPR Art. 27, we will appoint an EU representative and update this policy with their contact information.

---

**Acknowledgment:**
By using rMirror Cloud, you acknowledge that you have read and understood this Privacy Policy and consent to the collection, use, and disclosure of your personal data as described herein.
