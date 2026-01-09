# Legal Documents Summary

**Created:** January 9, 2026

## Overview

Two comprehensive legal documents have been prepared for rMirror Cloud to comply with Swiss and European data protection law:

1. **PRIVACY_POLICY.md** - User-facing privacy statement
2. **DATA_PROCESSING_AGREEMENT.md** - Technical DPA for B2B compliance

## Jurisdiction & Compliance

### Primary Legislation
- **Swiss Federal Act on Data Protection (FADP/revFADP)** - Effective September 1, 2023
- **EU General Data Protection Regulation (GDPR)** - Regulation (EU) 2016/679

### Transfer Mechanisms
- **Swiss-US Data Privacy Framework** - For transfers to US service providers
- **Standard Contractual Clauses (SCCs)** - EU Commission Decision 2021/914 + Swiss addendum

## Services Covered

### Third-Party Processors
All services are documented with data categories, locations, and legal safeguards:

| Service | Purpose | Location | Data | Safeguards |
|---------|---------|----------|------|------------|
| **Clerk** | Authentication | USA | Email, name, credentials | Swiss-US DPF, SCCs |
| **Anthropic** | OCR processing | USA | PDF images of pages | Swiss-US DPF, SCCs, No retention |
| **Resend** | Email delivery | USA | Email, notifications | Swiss-US DPF, SCCs |
| **Hetzner** | Infrastructure | Germany (EU) | All service data | GDPR compliant |
| **Backblaze B2** (optional) | File storage | USA | PDFs | Swiss-US DPF, SCCs, Encrypted |
| **Stripe** (Phase 2) | Payments | USA | Payment info | Swiss-US DPF, PCI DSS, SCCs |
| **Notion** (user-enabled) | Integration | USA | Notebook content | User consent, direct connection |

## Key Features

### Privacy Policy (PRIVACY_POLICY.md)
✅ **User Rights** (FADP Art. 25-32, GDPR Art. 12-22)
- Right to access, rectification, erasure, portability
- Right to restriction, objection, complaint
- Response time: 30 days (Swiss) / 1 month (EU)

✅ **Transparency**
- Clear data collection categories
- Purpose and legal basis for each processing activity
- Detailed Sub-processor information with privacy policy links
- Data retention periods specified

✅ **International Transfers**
- Explicit disclosure of US transfers
- Safeguards explained (DPF, SCCs, TIAs)
- User rights regarding transfers

✅ **Security Measures**
- Technical measures (encryption, access controls)
- Organizational measures (training, policies)
- Breach notification (72 hours)

✅ **Contact Information**
- Data Controller details
- Swiss FDPIC contact info
- Privacy-specific email address

### Data Processing Agreement (DATA_PROCESSING_AGREEMENT.md)
✅ **GDPR Art. 28 Compliance** (Processor obligations)
- Documented instructions
- Confidentiality commitments
- Security measures (Art. 32)
- Sub-processor management
- Data breach notification
- Assistance with Data Subject rights
- Audit rights

✅ **Swiss FADP Art. 9 Compliance** (Processor contracts)
- Controller-Processor relationship defined
- Cross-border disclosure provisions
- Swiss-specific legal requirements

✅ **Standard Contractual Clauses (SCCs)**
- EU SCCs Module 2 (Controller-to-Processor) incorporated
- Swiss SCCs with Swiss-specific addendum
- All three annexes completed:
  - Annex I: Details of processing
  - Annex II: Security measures
  - Annex III: Sub-processor list

✅ **Sub-Processor Management**
- Current Sub-processor list with details
- General authorization granted
- 30-day advance notice for changes
- 14-day objection period (30 days for EU)
- Right to terminate if objection not resolved

✅ **International Transfers**
- Swiss-US DPF as primary mechanism
- SCCs as alternative/supplementary
- Transfer Impact Assessments (TIAs) conducted
- Supplementary technical measures (encryption)
- Transparency on US government access

✅ **Liability & Indemnification**
- Processor liability cap (12 months fees)
- Exceptions for gross negligence/willful misconduct
- Indemnification for third-party claims
- Cooperation obligations

✅ **Termination & Data Deletion**
- 30-day grace period for data export
- Permanent deletion after grace period
- Deletion certification available
- Survival of key provisions

## Required Actions

### Immediate (Before Public Launch)
1. ✅ Review both documents with legal counsel
2. ⚠️ Add legal document links to website footer
3. ⚠️ Integrate into signup flow (checkbox acceptance)
4. ⚠️ Create `/privacy` and `/dpa` web pages
5. ⚠️ Add links in Terms of Service
6. ⚠️ Set up dedicated email addresses:
   - `privacy@rmirror.io`
   - `security@rmirror.io`

### Phase 2 (Before Stripe Launch)
7. ⚠️ Update documents to activate Stripe sections
8. ⚠️ Execute Stripe DPA
9. ⚠️ Update Sub-processor list in dashboard/emails

### Ongoing
10. ⚠️ Annual document review (or when services change)
11. ⚠️ Monitor DPF certifications of US Sub-processors
12. ⚠️ Maintain Sub-processor DPA register
13. ⚠️ Update documents within 30 days of new Sub-processors
14. ⚠️ Log data subject requests and responses

## Implementation Checklist

### Backend Integration
- [ ] Add privacy policy URL to API responses
- [ ] Add DPA acceptance tracking to user model
- [ ] Implement data export endpoints (JSON/CSV)
- [ ] Implement data deletion with 30-day grace period
- [ ] Add breach notification email templates
- [ ] Create audit log for data subject requests

### Dashboard Integration
- [ ] Add Privacy Policy page (`/privacy`)
- [ ] Add DPA page (`/dpa`)
- [ ] Add "Download My Data" button in settings
- [ ] Add "Delete My Account" button in settings (with 30-day warning)
- [ ] Display current Sub-processor list in settings
- [ ] Add Sub-processor change notification banner

### Agent Integration
- [ ] Display privacy policy link in setup wizard
- [ ] Show data collection notice on first run

### Email Templates
- [ ] Add privacy policy footer to all emails
- [ ] Create "Sub-processor Change" notification template
- [ ] Create "Data Export Ready" notification template
- [ ] Create "Account Deletion Confirmation" template

## Compliance Calendar

| Event | Frequency | Next Due |
|-------|-----------|----------|
| Privacy Policy review | Annual | January 2027 |
| DPA review | Annual | January 2027 |
| Sub-processor DPF verification | Quarterly | April 2026 |
| Security audit (SOC 2) | Annual | TBD |
| Staff privacy training | Annual | TBD |
| Data retention cleanup | Monthly | Auto-scheduled |
| Backup encryption verification | Quarterly | April 2026 |

## Contact & Support

### Supervisory Authority
**Swiss Federal Data Protection and Information Commissioner (FDPIC)**
- Website: https://www.edoeb.admin.ch/
- Email: info@edoeb.admin.ch
- Phone: +41 58 462 43 95

### Legal Resources
- Swiss FADP full text: https://www.admin.ch/opc/en/classified-compilation/19920153/index.html
- GDPR full text: https://gdpr-info.eu/
- Swiss-US DPF framework: https://www.dataprivacyframework.gov/
- EU SCC templates: https://ec.europa.eu/info/law/law-topic/data-protection/international-dimension-data-protection/standard-contractual-clauses-scc_en

## Notes for Legal Review

### Assumptions Made
1. **Data Controller Role:** Users are Controllers for their notebook data; rMirror is Processor
2. **No EU Representative Required:** Assumed under GDPR Art. 27 threshold (to be confirmed)
3. **No DPO Required:** Small organization, no large-scale systematic monitoring (to be confirmed)
4. **Swiss-US DPF Valid:** Assumed certifications current (verify quarterly)
5. **Backblaze Use:** Included as optional; confirm if actually deployed

### Areas for Customization
- [ ] Replace "Switzerland" with specific city/canton if required for FADP registration
- [ ] Add VAT/registration numbers if required
- [ ] Specify arbitration seat (Zurich suggested)
- [ ] Add company legal name if different from "rMirror Cloud"
- [ ] Confirm if EU representative needed (depends on EU user volume)

### Versioning
- Both documents include "Last Updated" dates
- Version history maintained at bottom of DPA
- Update version number when making changes
- Notify users of material changes (30 days advance)

## Questions for Legal Counsel

1. **Entity Structure:** Is rMirror Cloud a registered legal entity or sole proprietorship?
2. **EU Representative:** Do we need to appoint one under GDPR Art. 27?
3. **DPO Requirement:** Confirm exemption under GDPR Art. 37 / FADP Art. 10
4. **Stripe Timing:** Any legal prep needed before Phase 2 launch?
5. **Insurance:** Should we obtain cyber liability insurance?
6. **FDPIC Registration:** Is registration required for our data processing activities?
7. **Notion Integration:** Does user consent model suffice, or do we need separate agreements?
8. **OCR Content:** Are there additional obligations if users process sensitive categories of data in notebooks?

---

**Next Steps:**
1. Review with qualified Swiss data protection counsel
2. Make any necessary adjustments based on counsel feedback
3. Integrate into website and service flows
4. Execute Sub-processor DPAs with all vendors
5. Set up compliance monitoring and calendar
