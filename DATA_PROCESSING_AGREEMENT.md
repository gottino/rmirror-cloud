# Data Processing Agreement (DPA)

**Effective Date:** January 9, 2026
**Last Updated:** January 9, 2026

This Data Processing Agreement ("**DPA**") forms part of the Terms of Service between rMirror Cloud ("**Processor**," "**we**," "**us**," or "**our**") and you ("**Controller**," "**you**," or "**your**") governing the processing of Personal Data in connection with the rMirror Cloud service.

This DPA complies with:
- Swiss Federal Act on Data Protection (FADP/revFADP, effective September 1, 2023)
- EU General Data Protection Regulation (GDPR) Regulation (EU) 2016/679
- Standard Contractual Clauses approved by the European Commission and Swiss FDPIC

## 1. Definitions

**1.1** Terms used in this DPA have the meanings set forth below or as defined in the GDPR and Swiss FADP:

- **"Personal Data"** means any information relating to an identified or identifiable natural person processed by Processor on behalf of Controller through the Service.
- **"Processing"** means any operation performed on Personal Data, including collection, storage, use, disclosure, deletion, or destruction.
- **"Data Subject"** means the individual to whom Personal Data relates (i.e., the end user).
- **"Controller"** means you, the customer who determines the purposes and means of processing Personal Data.
- **"Processor"** means rMirror Cloud, which processes Personal Data on behalf of Controller.
- **"Sub-processor"** means any third-party processor engaged by Processor to process Personal Data.
- **"Service"** means the rMirror Cloud notebook synchronization and OCR transcription service.
- **"Supervisory Authority"** means the Swiss Federal Data Protection and Information Commissioner (FDPIC) or relevant EU Data Protection Authority.

## 2. Scope and Applicability

**2.1 Scope of Processing**
This DPA applies to all Processing of Personal Data by Processor on behalf of Controller in connection with the Service, including but not limited to:
- User account information
- Notebook content and metadata
- OCR transcription data
- Integration credentials and sync data
- Usage logs and analytics

**2.2 Controller-Processor Relationship**
The parties acknowledge that:
- **You (Controller)** determine the purposes and means of Processing your Personal Data
- **We (Processor)** process Personal Data solely on your behalf and in accordance with your documented instructions
- For your end users' Personal Data, you are the Controller and we are the Processor
- For your own account registration data, we act as Controller (governed by our Privacy Policy)

**2.3 Instructions**
Your instructions for Processing Personal Data include:
1. Use of the Service in accordance with the Terms of Service
2. Enabling/disabling integrations (Notion, etc.)
3. Managing quota and subscription settings
4. Data deletion requests
5. Any other instructions given through the Service interface or support channels

## 3. Processor's Obligations

**3.1 Processing in Accordance with Instructions**
Processor shall:
- Process Personal Data only on documented instructions from Controller (including this DPA and Terms of Service)
- Immediately inform Controller if instructions violate GDPR, FADP, or other data protection laws
- Not process Personal Data for any purpose other than Service delivery unless required by law

**3.2 Confidentiality**
Processor shall ensure that all personnel authorized to process Personal Data:
- Are bound by confidentiality obligations (contractual or statutory)
- Receive appropriate data protection training
- Access Personal Data only on a need-to-know basis

**3.3 Security of Processing**
Processor implements the following technical and organizational measures pursuant to Art. 32 GDPR and Art. 8 FADP:

#### 3.3.1 Technical Measures
| Measure | Implementation |
|---------|---------------|
| Encryption in Transit | TLS 1.3 for all API communications, web dashboard, and agent-server connections |
| Encryption at Rest | AES-256 encryption for PostgreSQL database and S3-compatible file storage |
| Access Control | Token-based API authentication (JWT), role-based access control (RBAC) |
| Network Security | Firewall rules, DDoS protection, isolated VPC for production infrastructure |
| Secure Deletion | Secure wipe of deleted data with 30-day grace period, overwrite on storage |
| Logging & Monitoring | Real-time security event logging, intrusion detection, automated alerts |
| Backup Security | Encrypted backups with separate encryption keys, 7-day retention |
| Vulnerability Management | Regular security patches, dependency scanning, penetration testing |

#### 3.3.2 Organizational Measures
| Measure | Implementation |
|---------|---------------|
| Access Management | Multi-factor authentication (MFA) for admin access, principle of least privilege |
| Personnel Security | Background checks for staff with data access, confidentiality agreements |
| Incident Response | Documented data breach response plan, 72-hour notification to Controller |
| Vendor Management | Due diligence on Sub-processors, DPA requirements in contracts |
| Security Training | Annual data protection training for all employees |
| Physical Security | Hetzner datacenter ISO 27001 certified, 24/7 monitoring, access logs |
| Data Minimization | Collect only necessary data, automated deletion of old logs (90 days) |

**3.4 Data Breach Notification**
In the event of a Personal Data breach, Processor shall:
1. **Notify Controller** without undue delay and within **72 hours** of becoming aware
2. Provide the following information (to the extent available):
   - Nature of the breach (categories and approximate number of Data Subjects affected)
   - Likely consequences of the breach
   - Measures taken or proposed to mitigate adverse effects
   - Contact point for further information
3. Cooperate with Controller in fulfilling Controller's obligations to notify Supervisory Authorities and Data Subjects
4. Document all breaches in an internal register

**3.5 Assistance with Controller Obligations**
Processor shall, taking into account the nature of Processing, assist Controller (by appropriate technical and organizational measures, where possible) in:

#### 3.5.1 Data Subject Rights (Art. 12-22 GDPR, Art. 25-32 FADP)
- **Access:** Provide exports of Personal Data in JSON/CSV format within 5 business days
- **Rectification:** Update incorrect data through dashboard or API within 2 business days
- **Erasure:** Permanently delete account and data within 30 days of request
- **Portability:** Export data in structured, machine-readable format (JSON/CSV)
- **Restriction:** Temporarily suspend processing while dispute is resolved
- **Objection:** Process objections to legitimate interest-based processing within 10 business days

Response time for assistance: **5 business days** (urgent requests: **48 hours**)

#### 3.5.2 Data Protection Impact Assessment (DPIA)
If required, Processor will provide:
- Description of Processing operations
- Security measures documentation
- Sub-processor information
- Transfer mechanism details

#### 3.5.3 Audits and Inspections
- Annual SOC 2 Type II audit reports (available upon request)
- Self-assessment questionnaires (CAIQ, SIG)
- Remote audit support (documentation review, Q&A)
- On-site audits (with 30 days' notice, maximum once per year, during business hours)

Audit costs:
- Remote audits: No charge
- On-site audits: Controller bears reasonable costs (travel, staff time beyond 8 hours)

**3.6 Deletion or Return of Personal Data**
Upon termination of Service or upon Controller's request:
1. **Data Export:** Processor provides full data export in JSON/CSV format (available for **30 days** post-termination)
2. **Deletion:** After 30-day grace period, Processor permanently deletes all Personal Data from production systems and backups
3. **Certification:** Upon request, Processor provides written certification of deletion
4. **Legal Retention:** Processor may retain copies required by law (e.g., tax records) in a secure, isolated environment

## 4. Sub-Processors

**4.1 General Authorization**
Controller grants general authorization to Processor to engage Sub-processors to assist in providing the Service. Current Sub-processors are listed in Section 4.2.

**4.2 Current Sub-Processors**

| Sub-processor | Service | Data Categories | Location | Safeguards |
|---------------|---------|-----------------|----------|------------|
| **Clerk Inc.** | Authentication & identity management | Email, name, authentication credentials | USA | Swiss-US DPF, SCCs, DPA |
| **Anthropic PBC** | OCR processing (handwriting transcription) | PDF images of notebook pages | USA | Swiss-US DPF, SCCs, DPA, No retention beyond processing |
| **Resend Inc.** | Transactional email delivery | Email address, name, notification content | USA | Swiss-US DPF, SCCs, DPA |
| **Hetzner Online GmbH** | Infrastructure hosting, database, storage | All service data | Germany (EU) | GDPR compliant, DPA |
| **Backblaze B2** (if configured) | Long-term file storage | Generated PDF files | USA | Swiss-US DPF, SCCs, DPA, Encrypted |
| **Stripe Inc.** (Phase 2, future) | Payment processing | Payment information, billing address | USA | Swiss-US DPF, PCI DSS Level 1, SCCs, DPA |

**4.3 Sub-Processor Obligations**
Processor ensures that each Sub-processor:
- Is bound by a Data Processing Agreement imposing substantially the same obligations as this DPA
- Implements appropriate technical and organizational security measures
- Provides adequate data protection guarantees for international transfers (SCCs, DPF)
- Permits audits and inspections
- Notifies Processor of any data breaches

**4.4 Sub-Processor Changes**
Processor shall:
1. **Notify Controller** of any intended changes (addition/replacement of Sub-processors) by:
   - Email notification to Controller's account email
   - Notice in dashboard (minimum **30 days** advance notice)
   - Updates to this DPA and Privacy Policy
2. **Allow Objection:** Controller may object to new Sub-processor within **14 days** of notification if Controller has reasonable data protection concerns
3. **Handle Objections:** If Controller objects:
   - Processor will discuss concerns in good faith
   - If unresolved, Controller may terminate Service without penalty and receive pro-rata refund

**4.5 Sub-Processor Liability**
Processor remains fully liable to Controller for the performance of Sub-processor obligations. Processor is responsible for the acts and omissions of Sub-processors to the same extent as if performed by Processor directly.

## 5. International Data Transfers

**5.1 Transfers Outside Switzerland and EU/EEA**
Personal Data may be transferred to and processed in the United States by Sub-processors listed in Section 4.2.

**5.2 Transfer Mechanisms**
Transfers are protected by the following safeguards:

#### 5.2.1 Swiss-US Data Privacy Framework
Sub-processors Clerk, Anthropic, Resend, and Stripe participate in the Swiss-US Data Privacy Framework, recognized by the Swiss FDPIC as providing adequate protection for transfers from Switzerland to the United States.

**Verification:** Processor maintains records of Sub-processor DPF certifications and provides upon request.

#### 5.2.2 Standard Contractual Clauses (SCCs)
For transfers not covered by adequacy decisions, Processor implements:
- **EU SCCs:** Commission Implementing Decision (EU) 2021/914 (Module 2: Controller-to-Processor)
- **Swiss SCCs:** Swiss FDPIC-approved SCCs with Swiss-specific addendum

**Supplementary Measures:**
- Transfer Impact Assessments (TIAs) conducted for each US Sub-processor
- Technical measures: End-to-end encryption, pseudonymization where feasible
- Contractual measures: Data access limitations, audit rights, breach notification
- Transparency: Sub-processor access requests and lawful orders disclosed (where legally permissible)

#### 5.2.3 Data Localization (EU Data)
For Controllers requiring data localization within the EU:
- Primary database and storage: Hetzner (Germany)
- OCR processing: Anthropic (USA) - temporary processing only, no retention
- Authentication: Clerk (USA) - no alternative available
- Email: Resend (USA) - metadata only

**Note:** Complete EU localization is not currently feasible due to essential US-based services (authentication). Controllers requiring strict EU localization should not use the Service.

**5.3 Controller Consent to Transfers**
By agreeing to this DPA, Controller:
- Consents to transfers described in Section 4.2
- Instructs Processor to execute SCCs on Controller's behalf where required
- Acknowledges receipt of information about transfer safeguards

**5.4 Changes to Transfer Mechanisms**
If transfer mechanisms are invalidated or materially changed:
- Processor will notify Controller within **7 days**
- Processor will implement alternative valid mechanisms within **30 days**
- If alternative mechanisms not feasible, Controller may terminate without penalty

## 6. Data Protection Officer (if applicable)

**6.1 Processor's DPO**
If Processor is required to appoint a Data Protection Officer under Art. 37 GDPR or Art. 10 FADP:
- Contact details will be provided here
- DPO responsible for monitoring compliance with this DPA

**Current Status:** As of January 2026, Processor is not required to appoint a DPO (small organization, no systematic large-scale monitoring).

**6.2 Controller's DPO**
If Controller has appointed a DPO, please provide contact details to: privacy@rmirror.io

## 7. Liability and Indemnification

**7.1 Processor Liability**
Processor shall be liable for damages caused by Processing where:
- Processor has not complied with GDPR/FADP obligations specifically directed at processors, OR
- Processor has acted outside or contrary to lawful instructions from Controller

**Liability Cap:**
- **Direct Damages:** Limited to fees paid by Controller in the 12 months preceding the claim
- **Indirect, Consequential, or Punitive Damages:** Excluded (except where prohibited by law)
- **Data Breach Damages:** Liability cap does not apply to damages arising from Processor's gross negligence or willful misconduct

**7.2 Indemnification**
Processor shall indemnify and hold harmless Controller from third-party claims arising from:
- Processor's breach of this DPA
- Processor's violation of data protection laws
- Sub-processor's breach (to the extent Processor is liable)

Indemnification does not cover claims arising from Controller's instructions, misuse of Service, or Controller's violation of laws.

**7.3 Cooperation**
Both parties shall cooperate in good faith to defend against third-party claims and minimize damages.

## 8. Duration and Termination

**8.1 Duration**
This DPA takes effect on the Effective Date and remains in force:
- As long as the Terms of Service remain in effect, AND
- Until Processor ceases all Processing of Personal Data on Controller's behalf

**8.2 Survival**
The following provisions survive termination:
- Section 3.6 (Deletion or Return of Personal Data)
- Section 7 (Liability and Indemnification)
- Section 9 (Governing Law and Dispute Resolution)

**8.3 Effect of Termination**
Upon termination:
1. Processor immediately ceases all Processing except as necessary for data return/deletion
2. Controller has **30 days** to export data
3. After 30 days, Processor permanently deletes all Personal Data (except legally required records)
4. Processor provides written certification of deletion upon request

## 9. Governing Law and Dispute Resolution

**9.1 Governing Law**
This DPA is governed by the laws of **Switzerland**, without regard to conflict of law principles.

**9.2 Disputes**
Any disputes arising from this DPA shall be resolved:
1. **First:** Good-faith negotiation between the parties (30 days)
2. **Second:** Mediation by Swiss Chambers' Arbitration Institution (30 days)
3. **Third:** Arbitration under Swiss Rules of International Arbitration
   - Seat: Zurich, Switzerland
   - Language: English
   - Number of arbitrators: One (1)
   - Award is final and binding

**9.3 Supervisory Authority Jurisdiction**
Nothing in this DPA limits Controller's or Data Subjects' right to:
- Lodge complaints with the Swiss FDPIC or relevant EU Data Protection Authority
- Seek judicial remedies under GDPR or FADP
- Pursue claims independently of this DPA

## 10. Amendments

**10.1 Material Amendments**
Material changes to this DPA require:
- **30 days' advance notice** to Controller
- Controller's continued use of Service constitutes acceptance
- Right to object and terminate within 30 days without penalty

**10.2 Non-Material Amendments**
Non-material changes (e.g., clarifications, formatting, updated contact details):
- Posted to website with updated "Last Updated" date
- Email notification within 7 days

**10.3 Legal Compliance Updates**
Amendments required by law or Supervisory Authority guidance:
- Implemented immediately without prior notice
- Notification provided within 7 days

## 11. General Provisions

**11.1 Entire Agreement**
This DPA, together with the Terms of Service and Privacy Policy, constitutes the entire agreement between the parties regarding data processing.

**11.2 Order of Precedence**
In case of conflict:
1. This DPA (data processing matters)
2. Terms of Service (general service matters)
3. Privacy Policy (supplementary information)

**11.3 Severability**
If any provision is held invalid, the remaining provisions remain in full force. Invalid provisions shall be replaced with valid provisions that achieve the closest legal equivalent.

**11.4 Assignment**
Controller may not assign this DPA without Processor's prior written consent. Processor may assign to a successor entity assuming all obligations.

**11.5 Waiver**
Failure to enforce any provision does not constitute a waiver of future enforcement.

**11.6 Force Majeure**
Neither party is liable for delays or failures due to causes beyond reasonable control (natural disasters, war, government action, internet outages), except payment obligations.

**11.7 Notices**
All notices under this DPA must be sent to:

**To Processor:**
Email: privacy@rmirror.io
Address: rMirror Cloud, Switzerland

**To Controller:**
Email address associated with Controller's account

## 12. Specific Provisions for EU/EEA Controllers

If Controller is established in the EU/EEA or processes data of EU/EEA Data Subjects:

**12.1 GDPR Compliance**
This DPA complies with Art. 28 GDPR (processor obligations). The parties are bound by the obligations in this DPA and the referenced Standard Contractual Clauses.

**12.2 EU Representative (if applicable)**
If required under GDPR Art. 27, Processor shall appoint an EU representative and update this DPA with contact details.

**12.3 Sub-processor Objection Period**
EU/EEA Controllers have **30 days** (instead of 14) to object to new Sub-processors.

## 13. Specific Provisions for Swiss Controllers

If Controller is established in Switzerland or processes data of Swiss Data Subjects:

**13.1 FADP Compliance**
This DPA complies with Art. 9 Swiss FADP (processor obligations). The parties acknowledge Swiss FADP standards may differ from GDPR in interpretation and enforcement.

**13.2 Cross-Border Data Disclosure**
Processor shall not disclose Personal Data to foreign authorities without Controller's prior consent, except where:
- Required by compulsory Swiss law
- Necessary for establishing, exercising, or defending legal claims

Processor shall, to the extent legally permissible:
- Notify Controller immediately of any request
- Challenge overly broad or unlawful requests
- Seek protective orders to limit disclosure

**13.3 Swiss DPA for Sub-processors**
All Sub-processors are bound by Swiss-compliant DPAs meeting FADP Art. 9 requirements.

## 14. Standard Contractual Clauses (SCCs)

**14.1 Incorporation by Reference**
The following Standard Contractual Clauses are incorporated into this DPA by reference:

1. **EU SCCs:** Commission Implementing Decision (EU) 2021/914
   - Module: Module Two (Controller-to-Processor)
   - Clauses: All mandatory clauses selected
   - Annexes completed as per Section 14.2 below

2. **Swiss SCCs:** Swiss FDPIC-approved SCCs (based on EU SCCs with Swiss addendum)
   - Supervisory Authority: Swiss FDPIC
   - Governing Law: Swiss law
   - Jurisdiction: Swiss courts

**14.2 SCC Annexes**

#### Annex I: Details of Processing

**A. List of Parties**

**Data Exporter (Controller):**
- Name: The customer (identified by account email)
- Address: As provided in account registration
- Contact: Account email address
- Activities: Use of rMirror Cloud service for notebook synchronization
- Role: Controller

**Data Importer (Processor):**
- Name: rMirror Cloud
- Address: Switzerland
- Contact: privacy@rmirror.io
- Activities: Cloud-based notebook synchronization, OCR transcription, integration management
- Role: Processor

**B. Description of Transfer**

**Categories of Data Subjects:**
- End users of rMirror Cloud service
- Individuals whose handwritten notes are processed through the service

**Categories of Personal Data:**
- Identity data: Name, email address
- Account data: Username, password hash, subscription tier
- Content data: Handwritten notes, notebook metadata, OCR transcription text
- Technical data: IP addresses, device information, usage logs
- Communication data: Email messages, support inquiries

**Sensitive Data (if applicable):**
- Special categories of data may be present in user-generated notebook content if user chooses to include such information (health data, religious beliefs, etc.)
- Processor has no knowledge of or control over sensitive data in notebooks

**Frequency of Transfer:**
- Continuous during active Service use (real-time synchronization)

**Nature of Processing:**
- Collection, storage, retrieval, transmission, erasure
- OCR transcription (automated processing)
- Integration synchronization (automated processing)

**Purpose of Transfer:**
- Provision of rMirror Cloud service as described in Terms of Service
- Synchronizing reMarkable notebooks to cloud
- Transcribing handwritten text via OCR
- Syncing content to third-party integrations (optional)

**Retention Period:**
- Duration of Service subscription + 30 days
- Or until deletion requested by Controller/Data Subject
- Logs: 90 days

**C. Competent Supervisory Authority**
- **For Swiss Controllers:** Swiss Federal Data Protection and Information Commissioner (FDPIC)
- **For EU Controllers:** Data Protection Authority of Controller's EU member state

#### Annex II: Technical and Organizational Measures

Refer to Section 3.3 of this DPA for detailed security measures.

**Summary:**
- Encryption: TLS 1.3 (transit), AES-256 (rest)
- Access control: RBAC, MFA, token-based authentication
- Network security: Firewalls, DDoS protection, VPC isolation
- Monitoring: Real-time logging, intrusion detection, automated alerts
- Backups: Encrypted, 7-day retention
- Personnel: Confidentiality agreements, security training
- Physical: ISO 27001 certified datacenter (Hetzner)

#### Annex III: Sub-processors

Refer to Section 4.2 of this DPA for current Sub-processor list.

**14.3 SCC Modifications and Optional Clauses**

**Docking Clause (Clause 7):** Not selected (no additional parties joining)

**Governing Law (Clause 17):**
- **EU SCCs:** Law of Ireland (EU member state)
- **Swiss SCCs:** Law of Switzerland

**Jurisdiction (Clause 18):**
- **EU SCCs:** Courts of Ireland
- **Swiss SCCs:** Courts of Switzerland (Zurich)

**Liability Cap (Clause 12.4):**
- Not selected (unlimited liability for damages caused by SCCs breach)

## 15. Contact Information

**Data Protection Inquiries:**
Email: privacy@rmirror.io

**Security Incidents:**
Email: security@rmirror.io

**General Support:**
Email: support@rmirror.io

**Supervisory Authority:**
Swiss Federal Data Protection and Information Commissioner (FDPIC)
Feldeggweg 1, 3003 Berne, Switzerland
Tel: +41 58 462 43 95
Email: info@edoeb.admin.ch
Website: https://www.edoeb.admin.ch/

---

## Acceptance

By using rMirror Cloud, Controller acknowledges having read, understood, and agreed to be bound by this Data Processing Agreement.

**Controller Acceptance:**
- Date: Upon first use of Service or acceptance of Terms of Service
- Method: Electronic acceptance via signup process

**Processor:**
rMirror Cloud
Switzerland
Date: January 9, 2026

---

**Document Version History:**
- v1.0 (2026-01-09): Initial version
