import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Privacy Policy - rMirror Cloud',
  description: 'Privacy Policy for rMirror Cloud. Learn how we collect, use, and protect your personal data.',
};

export default function PrivacyPolicyPage() {
  return (
    <article className="legal-prose" style={{ color: 'var(--warm-charcoal)' }}>
      <h1
        className="text-3xl font-bold mb-2"
        style={{ color: 'var(--warm-charcoal)' }}
      >
        Privacy Policy
      </h1>
      <p className="mb-8" style={{ color: 'var(--warm-gray)', fontSize: '0.925rem' }}>
        <strong>Effective Date:</strong> January 9, 2026 &middot;{' '}
        <strong>Last Updated:</strong> February 20, 2026
      </p>

      <div className="space-y-6" style={{ lineHeight: '1.75', fontSize: '0.95rem' }}>
        <Section title="1. Introduction">
          <p>
            rMirror Cloud (&ldquo;we,&rdquo; &ldquo;our,&rdquo; or &ldquo;us&rdquo;) is committed to protecting your
            privacy and personal data. This Privacy Policy explains how we collect, use, disclose, and safeguard your
            information when you use our service for reMarkable tablet notebook synchronization and transcription.
          </p>
          <div
            className="p-4 rounded-lg my-4"
            style={{ background: 'var(--soft-cream)', border: '1px solid var(--border)' }}
          >
            <p className="font-medium mb-1">Data Controller:</p>
            <p>
              Gabriele Ottino, operating as rMirror Cloud
              <br />
              Zurich, Switzerland
              <br />
              Email:{' '}
              <a href="mailto:privacy@rmirror.io" style={{ color: 'var(--terracotta)' }}>
                privacy@rmirror.io
              </a>
            </p>
          </div>
          <p>This Privacy Policy complies with:</p>
          <ul className="list-disc pl-6 space-y-1">
            <li>Swiss Federal Act on Data Protection (FADP/revFADP, effective September 1, 2023)</li>
            <li>EU General Data Protection Regulation (GDPR) where applicable</li>
            <li>Swiss-US Data Privacy Framework</li>
          </ul>
        </Section>

        <Section title="2. Information We Collect">
          <Subsection title="2.1 Account Information">
            <p>When you create an account, we collect:</p>
            <ul className="list-disc pl-6 space-y-1">
              <li>Email address</li>
              <li>Name</li>
              <li>Authentication credentials (managed by Clerk Inc.)</li>
              <li>Account creation date</li>
              <li>Subscription tier and billing status</li>
            </ul>
          </Subsection>

          <Subsection title="2.2 Notebook Content">
            <p>When you sync notebooks from your reMarkable tablet:</p>
            <ul className="list-disc pl-6 space-y-1">
              <li>Handwritten notes (binary .rm files)</li>
              <li>Notebook metadata (titles, creation dates, modification dates, folder structure)</li>
              <li>Generated PDFs of your notebook pages</li>
              <li>OCR-transcribed text from your handwritten notes</li>
            </ul>
          </Subsection>

          <Subsection title="2.3 Usage Data">
            <ul className="list-disc pl-6 space-y-1">
              <li>Quota usage (OCR pages processed)</li>
              <li>Sync history and timestamps</li>
              <li>API access logs</li>
              <li>Error reports and debugging information</li>
              <li>Web analytics via self-hosted Umami (page views, referrers, browser type, country &mdash; anonymous for non-logged-in visitors; linked to your user ID when logged in for service improvement and support)</li>
            </ul>
          </Subsection>

          <Subsection title="2.4 Integration Data">
            <p>If you connect third-party integrations:</p>
            <ul className="list-disc pl-6 space-y-1">
              <li>Integration service credentials (encrypted)</li>
              <li>Sync preferences and settings</li>
              <li>External service identifiers (e.g., Notion database IDs)</li>
            </ul>
          </Subsection>

          <Subsection title="2.5 Technical Data">
            <ul className="list-disc pl-6 space-y-1">
              <li>IP address</li>
              <li>Browser type and version</li>
              <li>Operating system</li>
              <li>Device information</li>
              <li>Access times and dates</li>
            </ul>
          </Subsection>
        </Section>

        <Section title="3. How We Use Your Information">
          <Subsection title="3.1 Service Delivery (Contractual Necessity)">
            <ul className="list-disc pl-6 space-y-1">
              <li>Synchronizing your reMarkable notebooks to the cloud</li>
              <li>Performing OCR transcription of your handwritten notes</li>
              <li>Generating searchable PDFs</li>
              <li>Managing your account and subscription</li>
              <li>Syncing to connected integrations (Notion, etc.)</li>
            </ul>
          </Subsection>

          <Subsection title="3.2 Communication (Contractual Necessity & Legitimate Interest)">
            <ul className="list-disc pl-6 space-y-1">
              <li>Sending service notifications (quota warnings, sync status)</li>
              <li>Responding to support inquiries</li>
              <li>Sending critical security updates</li>
            </ul>
          </Subsection>

          <Subsection title="3.3 Service Improvement (Legitimate Interest)">
            <ul className="list-disc pl-6 space-y-1">
              <li>Analyzing usage patterns to improve service performance</li>
              <li>Debugging technical issues</li>
              <li>Monitoring service health and reliability</li>
            </ul>
          </Subsection>

          <Subsection title="3.4 Legal Compliance (Legal Obligation)">
            <ul className="list-disc pl-6 space-y-1">
              <li>Complying with applicable laws and regulations</li>
              <li>Responding to lawful requests from authorities</li>
              <li>Protecting our legal rights</li>
            </ul>
          </Subsection>
        </Section>

        <Section title="4. Legal Basis for Processing (GDPR/FADP)">
          <p>We process your personal data based on:</p>
          <ul className="list-disc pl-6 space-y-2">
            <li>
              <strong>Contract (Art. 6(1)(b) GDPR):</strong> To create and manage your account, deliver the Service,
              and fulfill our contractual obligations to you
            </li>
            <li>
              <strong>Consent (Art. 6(1)(a) GDPR):</strong> For optional processing such as enabling third-party
              integrations (e.g., Notion sync). You may withdraw consent at any time without affecting prior processing
            </li>
            <li>
              <strong>Legitimate Interest (Art. 6(1)(f) GDPR):</strong> To improve and secure our service, analyze
              usage patterns, and debug technical issues
            </li>
            <li>
              <strong>Legal Obligation (Art. 6(1)(c) GDPR):</strong> To comply with Swiss and EU data protection laws
              and respond to lawful requests
            </li>
          </ul>
        </Section>

        <Section title="5. Third-Party Service Providers">
          <p>We use the following third-party processors to deliver our service:</p>

          <Subsection title="5.1 Authentication & Identity Management">
            <ServiceProvider
              name="Clerk Inc. (USA)"
              purpose="User authentication, account management"
              dataShared="Email address, name, authentication credentials"
              dataLocation="United States"
              safeguards="Swiss-US Data Privacy Framework participant; Standard Contractual Clauses (SCCs)"
              privacyUrl="https://clerk.com/privacy"
            />
          </Subsection>

          <Subsection title="5.2 OCR Processing">
            <ServiceProvider
              name="Anthropic PBC (USA) - Claude API"
              purpose="Optical Character Recognition (handwriting transcription)"
              dataShared="PDF images of notebook pages for OCR processing"
              dataLocation="United States"
              safeguards="Swiss-US Data Privacy Framework participant; Standard Contractual Clauses (SCCs)"
              privacyUrl="https://www.anthropic.com/privacy"
            />
            <p className="text-sm mt-2" style={{ color: 'var(--warm-gray)' }}>
              Anthropic retains API inputs and outputs for up to 7 days for operational purposes. Content flagged by
              trust and safety classifiers may be retained for up to 2 years. API data is not used for model training.
            </p>
          </Subsection>

          <Subsection title="5.3 Email Communications">
            <ServiceProvider
              name="Resend Inc. (USA)"
              purpose="Transactional email delivery (welcome emails, quota notifications)"
              dataShared="Email address, name, service usage data for notifications"
              dataLocation="United States"
              safeguards="Swiss-US Data Privacy Framework participant; Standard Contractual Clauses (SCCs)"
              privacyUrl="https://resend.com/privacy"
            />
          </Subsection>

          <Subsection title="5.4 Infrastructure Hosting">
            <ServiceProvider
              name="Hetzner Online GmbH (Germany)"
              purpose="Server infrastructure, database hosting, file storage"
              dataShared="All service data (notebooks, user data, database)"
              dataLocation="European Union (Germany)"
              safeguards="EU-based company, GDPR compliant"
              privacyUrl="https://www.hetzner.com/rechtliches/datenschutz"
            />
          </Subsection>

          <Subsection title="5.5 File Storage">
            <ServiceProvider
              name="Backblaze Inc. (USA) - Backblaze B2"
              purpose="Long-term storage of generated PDF files"
              dataShared="Generated PDF files of notebook pages"
              dataLocation="United States"
              safeguards="Encrypted at rest; Standard Contractual Clauses (SCCs)"
              privacyUrl="https://www.backblaze.com/company/policy/privacy"
            />
          </Subsection>

          <Subsection title="5.6 Optional User-Connected Integrations">
            <ServiceProvider
              name="Notion Labs Inc. (USA) - If you enable Notion sync"
              purpose="Syncing notebook content to your Notion workspace"
              dataShared="Notebook titles, page content, OCR text, metadata"
              dataLocation="United States (Notion's infrastructure)"
              safeguards="You explicitly authorize this connection and can disconnect anytime"
              privacyUrl="https://www.notion.so/privacy"
            />
          </Subsection>

          <p className="text-sm mt-4" style={{ color: 'var(--warm-gray)' }}>
            All third-party processors are bound by Data Processing Agreements (DPAs) requiring compliance with GDPR
            and Swiss FADP standards.
          </p>
        </Section>

        <Section title="6. International Data Transfers">
          <Subsection title="6.1 Transfers to the United States">
            <p>Your data may be transferred to and processed in the United States by:</p>
            <ul className="list-disc pl-6 space-y-1">
              <li>Clerk (authentication)</li>
              <li>Anthropic (OCR processing)</li>
              <li>Resend (email)</li>
              <li>Backblaze (file storage)</li>
              <li>Notion (if you enable integration)</li>
            </ul>
            <p className="mt-2"><strong>Safeguards for US Transfers:</strong></p>
            <ol className="list-decimal pl-6 space-y-1">
              <li>
                <strong>Swiss-US Data Privacy Framework:</strong> Our US service providers participate in this
                framework, providing adequacy for transfers from Switzerland
              </li>
              <li>
                <strong>Standard Contractual Clauses (SCCs):</strong> We execute SCCs approved by the Swiss FDPIC and
                EU Commission
              </li>
              <li>
                <strong>Supplementary Measures:</strong> We conduct Transfer Impact Assessments (TIAs) and implement
                technical safeguards (encryption, access controls)
              </li>
            </ol>
          </Subsection>

          <Subsection title="6.2 Transfers within the EU/EEA">
            <p>
              Data stored on Hetzner infrastructure remains within Germany (EU), providing adequacy under Swiss and EU
              law.
            </p>
          </Subsection>

          <Subsection title="6.3 Your Rights Regarding International Transfers">
            <p>You have the right to:</p>
            <ul className="list-disc pl-6 space-y-1">
              <li>Object to international data transfers</li>
              <li>Request information about safeguards in place</li>
              <li>Request a copy of applicable SCCs</li>
            </ul>
          </Subsection>
        </Section>

        <Section title="7. Data Retention">
          <p>We retain your personal data for the following periods:</p>
          <div className="overflow-x-auto my-4">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr style={{ borderBottom: '2px solid var(--border)' }}>
                  <th className="text-left py-2 pr-4 font-semibold">Data Type</th>
                  <th className="text-left py-2 pr-4 font-semibold">Retention Period</th>
                  <th className="text-left py-2 font-semibold">Justification</th>
                </tr>
              </thead>
              <tbody style={{ color: 'var(--warm-charcoal)' }}>
                <RetentionRow type="Account Information" period="Duration of account + 30 days after deletion" justification="Contractual necessity" />
                <RetentionRow type="Notebook Content" period="Duration of account + 30 days after deletion" justification="Service delivery" />
                <RetentionRow type="OCR Transcriptions" period="Duration of account + 30 days after deletion" justification="Service delivery" />
                <RetentionRow type="OCR Processing Data (at Anthropic)" period="Up to 7 days (up to 2 years if flagged)" justification="Sub-processor operational retention" />
                <RetentionRow type="Usage Logs" period="90 days" justification="Service improvement, security" />
                <RetentionRow type="Email Communications" period="2 years" justification="Legal compliance, support" />
                <RetentionRow type="Integration Credentials" period="Until disconnected by user" justification="Service functionality" />
              </tbody>
            </table>
          </div>
          <p>After these periods, data is permanently deleted from our systems and backups.</p>
        </Section>

        <Section title="8. Data Security">
          <Subsection title="8.1 Technical Measures">
            <ul className="list-disc pl-6 space-y-1">
              <li><strong>Encryption in Transit:</strong> TLS 1.3 for all data transmission</li>
              <li><strong>Encryption at Rest:</strong> AES-256 encryption for databases and file storage</li>
              <li>
                <strong>Access Controls:</strong> Role-based access control (RBAC), multi-factor authentication for
                admin access
              </li>
              <li><strong>API Security:</strong> Token-based authentication, rate limiting, input validation</li>
              <li>
                <strong>Secure Credential Storage:</strong> Integration credentials encrypted with separate encryption
                keys
              </li>
            </ul>
          </Subsection>

          <Subsection title="8.2 Organizational Measures">
            <ul className="list-disc pl-6 space-y-1">
              <li>rMirror Cloud is operated by a sole proprietor; only the operator has access to production systems and user data</li>
              <li>Data breach response procedures are in place (see Section 8.3)</li>
              <li>Periodic review of security configurations and access credentials</li>
              <li>Sub-processor security practices are evaluated before onboarding</li>
            </ul>
          </Subsection>

          <Subsection title="8.3 Data Breach Notification">
            <p>In the event of a data breach affecting your personal data, we will:</p>
            <ul className="list-disc pl-6 space-y-1">
              <li>Notify you within 72 hours of becoming aware</li>
              <li>Notify the Swiss Federal Data Protection and Information Commissioner (FDPIC) if required</li>
              <li>Provide details of the breach, potential impact, and mitigation measures</li>
            </ul>
          </Subsection>
        </Section>

        <Section title="9. Your Rights Under Swiss FADP and GDPR">
          <p>You have the following rights regarding your personal data:</p>

          <Subsection title="9.1 Right to Access (Art. 25 FADP, Art. 15 GDPR)">
            <p>Request confirmation of what personal data we process and obtain a copy.</p>
          </Subsection>

          <Subsection title="9.2 Right to Rectification (Art. 32 FADP, Art. 16 GDPR)">
            <p>Request correction of inaccurate or incomplete personal data.</p>
          </Subsection>

          <Subsection title="9.3 Right to Erasure / Right to be Forgotten (Art. 32 FADP, Art. 17 GDPR)">
            <p>
              You can delete your account and all associated data at any time directly through the dashboard (see our{' '}
              <a href="/legal/terms" style={{ color: 'var(--terracotta)' }}>Terms of Service</a>, Section 13.1).
              Deletion is immediate and irreversible. You may also request partial deletion of specific data (e.g.,
              individual notebooks) without deleting your account by contacting{' '}
              <a href="mailto:privacy@rmirror.io" style={{ color: 'var(--terracotta)' }}>privacy@rmirror.io</a>.
            </p>
          </Subsection>

          <Subsection title="9.4 Right to Data Portability (Art. 28 FADP, Art. 20 GDPR)">
            <p>Receive your personal data in a structured, machine-readable format (JSON/CSV).</p>
          </Subsection>

          <Subsection title="9.5 Right to Restriction of Processing (Art. 18 GDPR)">
            <p>
              Request limitation of processing in certain circumstances. Note: The Swiss FADP does not provide an
              explicit equivalent right to restriction, but we honor such requests as a matter of good practice.
            </p>
          </Subsection>

          <Subsection title="9.6 Right to Object (Art. 30(2)(b) FADP, Art. 21 GDPR)">
            <p>Object to processing based on legitimate interests or direct marketing.</p>
          </Subsection>

          <Subsection title="9.7 Right to Withdraw Consent">
            <p>Withdraw consent at any time (without affecting prior processing).</p>
          </Subsection>

          <Subsection title="9.8 Right to Lodge a Complaint">
            <p>File a complaint with:</p>
            <ul className="list-disc pl-6 space-y-1">
              <li>
                <strong>Switzerland:</strong> Federal Data Protection and Information Commissioner (FDPIC) &mdash;{' '}
                <a
                  href="https://www.edoeb.admin.ch/"
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: 'var(--terracotta)' }}
                >
                  edoeb.admin.ch
                </a>
              </li>
              <li><strong>EU:</strong> Your local Data Protection Authority</li>
            </ul>
          </Subsection>

          <Subsection title="9.9 Exercising Your Rights">
            <p>
              To exercise any of these rights, contact us at:{' '}
              <a href="mailto:privacy@rmirror.io" style={{ color: 'var(--terracotta)' }}>
                privacy@rmirror.io
              </a>
            </p>
            <p>We will respond within:</p>
            <ul className="list-disc pl-6 space-y-1">
              <li><strong>30 days</strong> (Swiss FADP standard)</li>
              <li><strong>1 month</strong> (GDPR standard, extendable to 3 months for complex requests)</li>
            </ul>
          </Subsection>
        </Section>

        <Section title="10. Children&apos;s Privacy">
          <p>
            rMirror Cloud is not intended for children under 16 years of age. We do not knowingly collect personal data
            from children. If you believe we have inadvertently collected data from a child, contact us immediately for
            deletion.
          </p>
        </Section>

        <Section title="11. Cookies and Tracking">
          <Subsection title="11.1 Essential Cookies">
            <p>We use essential cookies strictly necessary for the Service to function:</p>
            <div className="overflow-x-auto my-4">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr style={{ borderBottom: '2px solid var(--border)' }}>
                    <th className="text-left py-2 pr-4 font-semibold">Cookie</th>
                    <th className="text-left py-2 pr-4 font-semibold">Provider</th>
                    <th className="text-left py-2 pr-4 font-semibold">Purpose</th>
                    <th className="text-left py-2 font-semibold">Duration</th>
                  </tr>
                </thead>
                <tbody style={{ color: 'var(--warm-charcoal)' }}>
                  <CookieRow cookie="__session" provider="Clerk" purpose="Authentication session management" duration="Session / up to 7 days" />
                  <CookieRow cookie="__client_uat" provider="Clerk" purpose="Client-side authentication state" duration="Session" />
                  <CookieRow cookie="__clerk_db_jwt" provider="Clerk" purpose="Authentication token (development only)" duration="Session" />
                  <CookieRow cookie="CSRF token" provider="rMirror Cloud" purpose="Cross-site request forgery protection" duration="Session" />
                </tbody>
              </table>
            </div>
          </Subsection>

          <Subsection title="11.2 Web Analytics">
            <p>
              We use a <strong>self-hosted instance of Umami</strong> for web analytics on the dashboard. Umami is
              privacy-focused and:
            </p>
            <ul className="list-disc pl-6 space-y-1">
              <li>Does <strong>not</strong> use cookies</li>
              <li>Does <strong>not</strong> collect IP addresses</li>
              <li>Does <strong>not</strong> track users across sites</li>
              <li>Does <strong>not</strong> store any data in your browser</li>
            </ul>
            <p>
              <strong>For visitors who are not logged in:</strong> Analytics data is fully anonymous and aggregated
              (page views, referrers, browser type, country). This data cannot be used to identify individual users.
            </p>
            <p>
              <strong>For logged-in users:</strong> We associate analytics events (such as feature usage, onboarding
              progress, and integration activity) with your Clerk user ID to understand how individual users interact
              with the dashboard. This allows us to improve the Service and provide better user support (e.g.,
              diagnosing issues you report). The legal basis for this is{' '}
              <strong>legitimate interest</strong> (Art. 6(1)(f) GDPR). You can object to this processing by
              contacting{' '}
              <a href="mailto:privacy@rmirror.io" style={{ color: 'var(--terracotta)' }}>
                privacy@rmirror.io
              </a>
              .
            </p>
            <p>
              <strong>Data location:</strong> All analytics data is stored on our self-hosted Umami instance on Hetzner
              infrastructure in Germany (EU). No analytics data is shared with third parties.
            </p>
            <p>We do not use advertising, marketing, or non-essential tracking cookies.</p>
          </Subsection>

          <Subsection title="11.3 Browser Controls">
            <p>
              You can control cookies through your browser settings. Blocking essential cookies may impair service
              functionality.
            </p>
          </Subsection>
        </Section>

        <Section title="12. Automated Decision-Making">
          <p>
            We do not use automated decision-making or profiling that produces legal effects or similarly significant
            effects on you (Art. 21 FADP, Art. 22 GDPR). OCR transcription is automated processing, but it does not
            produce decisions with legal or similarly significant effects. If we introduce automated decision-making in
            the future, we will update this Privacy Policy and provide you with the right to contest such decisions and
            request human review.
          </p>
        </Section>

        <Section title="13. Changes to This Privacy Policy">
          <p>We may update this Privacy Policy to reflect:</p>
          <ul className="list-disc pl-6 space-y-1">
            <li>Changes in our data practices</li>
            <li>New features or services</li>
            <li>Legal or regulatory requirements</li>
          </ul>
          <p className="mt-2"><strong>Notification of Changes:</strong></p>
          <ul className="list-disc pl-6 space-y-1">
            <li>Material changes: Email notification + prominent notice in dashboard</li>
            <li>Non-material changes: Updated &ldquo;Last Updated&rdquo; date</li>
          </ul>
        </Section>

        <Section title="14. Data Controller Contact Information">
          <div
            className="p-4 rounded-lg"
            style={{ background: 'var(--soft-cream)', border: '1px solid var(--border)' }}
          >
            <p className="font-medium mb-1">Data Controller:</p>
            <p>
              Gabriele Ottino, operating as rMirror Cloud
              <br />
              Zurich, Switzerland
              <br />
              Email:{' '}
              <a href="mailto:privacy@rmirror.io" style={{ color: 'var(--terracotta)' }}>
                privacy@rmirror.io
              </a>
            </p>
          </div>
        </Section>

        <Section title="15. Supervisory Authority">
          <p><strong>Switzerland:</strong></p>
          <p>
            Federal Data Protection and Information Commissioner (FDPIC)
            <br />
            Feldeggweg 1, 3003 Berne, Switzerland
            <br />
            Tel: +41 58 462 43 95
            <br />
            Email:{' '}
            <a href="mailto:info@edoeb.admin.ch" style={{ color: 'var(--terracotta)' }}>
              info@edoeb.admin.ch
            </a>
            <br />
            Website:{' '}
            <a
              href="https://www.edoeb.admin.ch/"
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: 'var(--terracotta)' }}
            >
              edoeb.admin.ch
            </a>
          </p>
          <p className="mt-2">
            <strong>EU (if applicable):</strong> Contact your local Data Protection Authority
          </p>
        </Section>

        <Section title="16. Additional Information for EU/EEA Users">
          <Subsection title="16.1 Legal Basis Summary">
            <div className="overflow-x-auto my-4">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr style={{ borderBottom: '2px solid var(--border)' }}>
                    <th className="text-left py-2 pr-4 font-semibold">Processing Activity</th>
                    <th className="text-left py-2 font-semibold">Legal Basis</th>
                  </tr>
                </thead>
                <tbody style={{ color: 'var(--warm-charcoal)' }}>
                  <LegalBasisRow activity="Account creation and management" basis="Contract (Art. 6(1)(b))" />
                  <LegalBasisRow activity="Notebook sync and OCR" basis="Contract (Art. 6(1)(b))" />
                  <LegalBasisRow activity="Email notifications (service-related)" basis="Contract (Art. 6(1)(b)), Legitimate Interest (Art. 6(1)(f))" />
                  <LegalBasisRow activity="Integration sync (Notion, etc.)" basis="Consent (Art. 6(1)(a))" />
                  <LegalBasisRow activity="Service improvement and analytics (including anonymous Umami web analytics)" basis="Legitimate Interest (Art. 6(1)(f))" />
                  <LegalBasisRow activity="Legal compliance" basis="Legal Obligation (Art. 6(1)(c))" />
                </tbody>
              </table>
            </div>
          </Subsection>

          <Subsection title="16.2 Legitimate Interest Balancing">
            <p>
              Where we rely on legitimate interests, we have conducted balancing tests demonstrating our interests do
              not override your fundamental rights and freedoms.
            </p>
          </Subsection>

          <Subsection title="16.3 Representative in the EU">
            <p>
              If required under GDPR Art. 27, we will appoint an EU representative and update this policy with their
              contact information.
            </p>
          </Subsection>
        </Section>

        <hr className="my-8" style={{ borderColor: 'var(--border)' }} />

        <p>
          <strong>
            By using rMirror Cloud, you acknowledge that you have read and understood this Privacy Policy.
          </strong>
        </p>
      </div>
    </article>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-4">
      <h2
        className="text-xl font-semibold pt-4 border-t"
        style={{ color: 'var(--warm-charcoal)', borderColor: 'var(--border)' }}
      >
        {title}
      </h2>
      {children}
    </section>
  );
}

function Subsection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <h3 className="text-base font-medium" style={{ color: 'var(--warm-charcoal)' }}>
        {title}
      </h3>
      {children}
    </div>
  );
}

function ServiceProvider({
  name,
  purpose,
  dataShared,
  dataLocation,
  safeguards,
  privacyUrl,
}: {
  name: string;
  purpose: string;
  dataShared: string;
  dataLocation: string;
  safeguards: string;
  privacyUrl: string;
}) {
  return (
    <div
      className="p-4 rounded-lg text-sm space-y-1"
      style={{ background: 'var(--soft-cream)', border: '1px solid var(--border)' }}
    >
      <p className="font-medium">{name}</p>
      <p><strong>Purpose:</strong> {purpose}</p>
      <p><strong>Data Shared:</strong> {dataShared}</p>
      <p><strong>Data Location:</strong> {dataLocation}</p>
      <p><strong>Safeguards:</strong> {safeguards}</p>
      <p>
        <a href={privacyUrl} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--terracotta)' }}>
          Privacy Policy
        </a>
      </p>
    </div>
  );
}

function RetentionRow({
  type,
  period,
  justification,
}: {
  type: string;
  period: string;
  justification: string;
}) {
  return (
    <tr style={{ borderBottom: '1px solid var(--border)' }}>
      <td className="py-2 pr-4">{type}</td>
      <td className="py-2 pr-4">{period}</td>
      <td className="py-2">{justification}</td>
    </tr>
  );
}

function CookieRow({
  cookie,
  provider,
  purpose,
  duration,
}: {
  cookie: string;
  provider: string;
  purpose: string;
  duration: string;
}) {
  return (
    <tr style={{ borderBottom: '1px solid var(--border)' }}>
      <td className="py-2 pr-4"><code style={{ fontSize: '0.85em' }}>{cookie}</code></td>
      <td className="py-2 pr-4">{provider}</td>
      <td className="py-2 pr-4">{purpose}</td>
      <td className="py-2">{duration}</td>
    </tr>
  );
}

function LegalBasisRow({ activity, basis }: { activity: string; basis: string }) {
  return (
    <tr style={{ borderBottom: '1px solid var(--border)' }}>
      <td className="py-2 pr-4">{activity}</td>
      <td className="py-2">{basis}</td>
    </tr>
  );
}
