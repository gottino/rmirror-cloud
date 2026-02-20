import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Terms of Service - rMirror Cloud',
  description: 'Terms of Service for rMirror Cloud, a cloud service for reMarkable tablet integration.',
};

export default function TermsOfServicePage() {
  return (
    <article className="legal-prose" style={{ color: 'var(--warm-charcoal)' }}>
      <h1
        className="text-3xl font-bold mb-2"
        style={{ color: 'var(--warm-charcoal)' }}
      >
        Terms of Service
      </h1>
      <p className="mb-8" style={{ color: 'var(--warm-gray)', fontSize: '0.925rem' }}>
        <strong>Effective Date:</strong> February 20, 2026 &middot;{' '}
        <strong>Last Updated:</strong> February 20, 2026
      </p>

      <div className="space-y-6" style={{ lineHeight: '1.75', fontSize: '0.95rem' }}>
        <p>
          These Terms of Service (&ldquo;<strong>Terms</strong>&rdquo;) govern your access to and use of the rMirror Cloud
          service (&ldquo;<strong>Service</strong>&rdquo;) operated by rMirror Cloud (&ldquo;<strong>we</strong>,&rdquo;
          &ldquo;<strong>us</strong>,&rdquo; or &ldquo;<strong>our</strong>&rdquo;). By creating an account or using the
          Service, you agree to be bound by these Terms.
        </p>
        <p>
          <strong>Please read these Terms carefully.</strong> If you do not agree, do not use the Service.
        </p>

        <Section title="1. About the Service">
          <Subsection title="1.1 Description">
            <p>
              rMirror Cloud is a cloud-based service that synchronizes notebooks from reMarkable tablets, performs
              optical character recognition (OCR) on handwritten notes, and optionally syncs content to third-party
              services such as Notion. The Service consists of:
            </p>
            <ul className="list-disc pl-6 space-y-1">
              <li>A cloud backend (API and processing)</li>
              <li>A web dashboard for viewing notebooks and managing settings</li>
              <li>A desktop agent (macOS application) for automatic synchronization</li>
            </ul>
          </Subsection>

          <Subsection title="1.2 Beta Status">
            <p>
              The Service is currently provided as a <strong>beta / early access</strong> offering. This means:
            </p>
            <ul className="list-disc pl-6 space-y-1">
              <li>Features may change, be added, or be removed without advance notice</li>
              <li>The Service may experience interruptions, bugs, or data loss</li>
              <li>We do not guarantee any particular level of availability or performance</li>
              <li>We welcome your feedback to help improve the Service</li>
            </ul>
          </Subsection>

          <Subsection title="1.3 Open Source">
            <p>
              The source code of rMirror Cloud is available under the GNU Affero General Public License v3 (AGPL-3.0).
              These Terms govern only your use of the <strong>hosted Service</strong> operated by us. If you choose to
              self-host the software, the AGPL-3.0 license applies to your use of the code, but these Terms do not apply
              to self-hosted instances.
            </p>
          </Subsection>
        </Section>

        <Section title="2. Account Registration">
          <Subsection title="2.1 Eligibility">
            <p>
              You must be at least <strong>16 years of age</strong> to use the Service. By registering, you represent
              that you meet this requirement.
            </p>
          </Subsection>

          <Subsection title="2.2 Account Responsibilities">
            <p>You are responsible for:</p>
            <ul className="list-disc pl-6 space-y-1">
              <li>Providing accurate and current registration information</li>
              <li>Maintaining the confidentiality of your account credentials</li>
              <li>All activity that occurs under your account</li>
              <li>
                Notifying us promptly at{' '}
                <a href="mailto:support@rmirror.io" style={{ color: 'var(--terracotta)' }}>
                  support@rmirror.io
                </a>{' '}
                if you suspect unauthorized access
              </li>
            </ul>
          </Subsection>

          <Subsection title="2.3 Account Security">
            <p>
              Authentication is managed by our third-party provider, Clerk Inc. You agree to use strong, unique passwords
              and to enable additional security features where available. We are not responsible for losses arising from
              your failure to secure your credentials.
            </p>
          </Subsection>
        </Section>

        <Section title="3. Service Tiers and Quotas">
          <Subsection title="3.1 Free Tier">
            <p>The free tier includes:</p>
            <ul className="list-disc pl-6 space-y-1">
              <li>Up to <strong>30 OCR-processed pages per month</strong></li>
              <li>Notebook synchronization and PDF generation</li>
              <li>Access to the web dashboard</li>
              <li>Optional integration connections (e.g., Notion)</li>
            </ul>
            <p>
              Quota resets monthly. When your quota is exhausted, the Service continues to accept notebook uploads and
              generate PDFs, but OCR processing and integration syncs are deferred until quota resets or you upgrade.
            </p>
          </Subsection>

          <Subsection title="3.2 Paid Tiers (Coming Soon)">
            <p>
              We intend to offer paid subscription plans with higher quotas and additional features. Details, pricing,
              and payment terms will be communicated before launch and added to these Terms.
            </p>
          </Subsection>

          <Subsection title="3.3 Changes to Tiers">
            <p>
              We reserve the right to modify, add, or discontinue service tiers, quotas, and features. For material
              changes that reduce functionality of your current tier:
            </p>
            <ul className="list-disc pl-6 space-y-1">
              <li>We will provide at least <strong>30 days&apos; advance notice</strong> via email</li>
              <li>
                If you are on a paid plan and disagree with the change, you may cancel before the change takes effect
              </li>
            </ul>
          </Subsection>
        </Section>

        <Section title="4. Paid Subscriptions (When Applicable)">
          <Subsection title="4.1 Billing">
            <p>
              Paid subscriptions are billed on a recurring basis (monthly or annually, as selected). Payment is processed
              by Stripe Inc. By subscribing, you authorize us to charge your payment method at the beginning of each
              billing cycle.
            </p>
          </Subsection>

          <Subsection title="4.2 No Refunds">
            <p>
              All subscription fees are <strong>non-refundable</strong>. When you cancel a paid subscription, you retain
              access to paid features until the end of your current billing period. No partial refunds are provided for
              unused portions of a billing cycle.
            </p>
            <p>
              <strong>Note for EU/Swiss consumers:</strong> If you are a consumer in the EU or Switzerland, you may have
              a statutory right of withdrawal within 14 days of your initial subscription purchase, provided you have not
              fully used the Service during that period. To exercise this right, contact us at{' '}
              <a href="mailto:support@rmirror.io" style={{ color: 'var(--terracotta)' }}>
                support@rmirror.io
              </a>{' '}
              within 14 days of purchase.
            </p>
          </Subsection>

          <Subsection title="4.3 Price Changes">
            <p>
              We may change subscription prices with at least <strong>30 days&apos; advance notice</strong>. Price
              changes take effect at the start of your next billing cycle. If you do not agree with the new price, you
              may cancel before renewal.
            </p>
          </Subsection>

          <Subsection title="4.4 Failed Payments">
            <p>
              If a payment fails, we will attempt to charge your payment method again. If payment remains unsuccessful
              after reasonable attempts, we may downgrade your account to the free tier. We will notify you by email
              before any downgrade.
            </p>
          </Subsection>
        </Section>

        <Section title="5. Your Content">
          <Subsection title="5.1 Ownership">
            <p>
              You retain full ownership of all content you upload, sync, or create through the Service (&ldquo;
              <strong>Your Content</strong>&rdquo;), including notebooks, handwritten notes, OCR transcriptions, and
              metadata. We claim no intellectual property rights over Your Content.
            </p>
          </Subsection>

          <Subsection title="5.2 License to Us">
            <p>
              By using the Service, you grant us a limited, non-exclusive, worldwide license to store, process, transmit,
              and display Your Content solely as necessary to provide and improve the Service. This includes:
            </p>
            <ul className="list-disc pl-6 space-y-1">
              <li>Storing notebook files and generated PDFs on our servers</li>
              <li>Transmitting page images to Anthropic for OCR processing</li>
              <li>Syncing content to third-party integrations you have enabled</li>
            </ul>
            <p>This license terminates when you delete Your Content or your account.</p>
          </Subsection>

          <Subsection title="5.3 Content Restrictions">
            <p>You agree not to upload, sync, or transmit content that:</p>
            <ul className="list-disc pl-6 space-y-1">
              <li>Violates any applicable law or regulation</li>
              <li>Infringes on the intellectual property rights of others</li>
              <li>Contains malware, viruses, or harmful code</li>
              <li>Is intended to disrupt, overload, or attack the Service or its infrastructure</li>
            </ul>
          </Subsection>

          <Subsection title="5.4 Content Responsibility">
            <p>
              You are solely responsible for the content of your notebooks. We do not pre-screen, review, or monitor
              Your Content. We have no knowledge of or control over what you write in your notebooks.
            </p>
          </Subsection>
        </Section>

        <Section title="6. Acceptable Use">
          <p>You agree not to:</p>
          <ul className="list-disc pl-6 space-y-1">
            <li>Use the Service for any unlawful purpose</li>
            <li>Attempt to gain unauthorized access to the Service, other accounts, or related systems</li>
            <li>
              Reverse-engineer, decompile, or disassemble any part of the Service (except as permitted by the AGPL-3.0
              license for the open source code)
            </li>
            <li>
              Use automated tools to access the Service in a manner that exceeds reasonable use (e.g., excessive API
              calls)
            </li>
            <li>Resell, sublicense, or commercially exploit the Service without our written permission</li>
            <li>Interfere with or disrupt the Service or impose an unreasonable load on our infrastructure</li>
            <li>Circumvent any access controls, quotas, or rate limits</li>
          </ul>
        </Section>

        <Section title="7. Third-Party Integrations">
          <Subsection title="7.1 Optional Integrations">
            <p>
              The Service allows you to connect third-party services (e.g., Notion) to sync your notebook content. These
              integrations are optional and initiated by you.
            </p>
          </Subsection>

          <Subsection title="7.2 Third-Party Terms">
            <p>
              When you enable an integration, you are also subject to the third-party service&apos;s terms and privacy
              policy. We are not responsible for the practices, content, or availability of third-party services.
            </p>
          </Subsection>

          <Subsection title="7.3 Credentials">
            <p>
              You provide integration credentials (e.g., API keys, OAuth tokens) to enable syncing. We store these
              encrypted and use them solely to perform the sync you requested. You may revoke integration access at any
              time through the dashboard.
            </p>
          </Subsection>
        </Section>

        <Section title="8. Intellectual Property">
          <Subsection title="8.1 Service IP">
            <p>
              Apart from Your Content and open source components licensed under AGPL-3.0, all rights in the Service
              (including its design, branding, documentation, and proprietary elements) are owned by us.
            </p>
          </Subsection>

          <Subsection title="8.2 Trademarks">
            <p>
              &ldquo;rMirror Cloud&rdquo; and associated logos are our trademarks. You may not use them without our prior
              written permission, except as necessary to refer to the Service.
            </p>
          </Subsection>

          <Subsection title="8.3 Feedback">
            <p>
              If you provide feedback, suggestions, or ideas about the Service, you grant us a non-exclusive,
              royalty-free, perpetual license to use and incorporate that feedback without obligation to you.
            </p>
          </Subsection>
        </Section>

        <Section title="9. Privacy and Data Protection">
          <Subsection title="9.1 Privacy Policy">
            <p>
              Our collection and use of personal data is governed by our{' '}
              <a href="/legal/privacy" style={{ color: 'var(--terracotta)' }}>
                Privacy Policy
              </a>
              . By using the Service, you acknowledge you have read and understood the Privacy Policy.
            </p>
          </Subsection>

          <Subsection title="9.2 Data Processing Agreement">
            <p>
              For users who are data controllers (e.g., businesses processing personal data through the Service), our
              Data Processing Agreement applies.
            </p>
          </Subsection>

          <Subsection title="9.3 Data Location">
            <p>
              Your data is primarily stored on servers in Germany (EU). Certain processing (OCR, authentication, email)
              involves transfers to the United States. Details are provided in the Privacy Policy and DPA.
            </p>
          </Subsection>
        </Section>

        <Section title="10. Disclaimer of Warranties">
          <Subsection title="10.1 &ldquo;As Is&rdquo; Service">
            <p className="uppercase text-sm" style={{ fontWeight: 500 }}>
              The Service is provided on an &ldquo;as is&rdquo; and &ldquo;as available&rdquo; basis, without warranties
              of any kind, whether express, implied, or statutory. To the maximum extent permitted by applicable law, we
              disclaim all warranties, including but not limited to:
            </p>
            <ul className="list-disc pl-6 space-y-1">
              <li>Implied warranties of merchantability, fitness for a particular purpose, and non-infringement</li>
              <li>
                That the Service will be uninterrupted, secure, error-free, or free of harmful components
              </li>
              <li>That OCR results will be accurate or complete</li>
              <li>That data will not be lost or corrupted</li>
            </ul>
          </Subsection>

          <Subsection title="10.2 Beta Disclaimer">
            <p>
              Given the beta status of the Service, you acknowledge that bugs, data loss, and service interruptions are
              more likely than in a mature product. <strong>You should maintain your own backups of important data</strong>{' '}
              and not rely solely on the Service for data preservation.
            </p>
          </Subsection>

          <Subsection title="10.3 No Professional Advice">
            <p>
              The Service provides OCR transcription of handwritten text. It does not provide and should not be relied
              upon for legal, medical, financial, or other professional advice based on the content of your notebooks.
            </p>
          </Subsection>
        </Section>

        <Section title="11. Limitation of Liability">
          <Subsection title="11.1 Liability Cap">
            <p className="uppercase text-sm" style={{ fontWeight: 500 }}>
              To the maximum extent permitted by applicable law, our total aggregate liability to you for all claims
              arising from or related to the Service shall not exceed the greater of:
            </p>
            <ul className="list-disc pl-6 space-y-1">
              <li>
                The total fees you have paid to us in the <strong>12 months</strong> preceding the claim, or
              </li>
              <li>
                <strong>CHF 100</strong> (one hundred Swiss francs)
              </li>
            </ul>
          </Subsection>

          <Subsection title="11.2 Exclusion of Damages">
            <p className="uppercase text-sm" style={{ fontWeight: 500 }}>
              To the maximum extent permitted by applicable law, we shall not be liable for any indirect, incidental,
              special, consequential, or punitive damages, including but not limited to:
            </p>
            <ul className="list-disc pl-6 space-y-1">
              <li>Loss of profits, revenue, or data</li>
              <li>Business interruption</li>
              <li>Cost of substitute services</li>
              <li>Damages arising from loss of or corruption to Your Content</li>
            </ul>
          </Subsection>

          <Subsection title="11.3 Exceptions">
            <p>Nothing in these Terms excludes or limits liability for:</p>
            <ul className="list-disc pl-6 space-y-1">
              <li>Death or personal injury caused by negligence</li>
              <li>Fraud or fraudulent misrepresentation</li>
              <li>Gross negligence or willful misconduct</li>
              <li>Any liability that cannot be excluded under applicable Swiss or EU law</li>
            </ul>
          </Subsection>

          <Subsection title="11.4 Consumer Protection">
            <p>
              If you are a consumer in Switzerland or the EU, the limitations and exclusions in this section apply only
              to the extent permitted by mandatory consumer protection law in your jurisdiction. Mandatory statutory
              rights are not affected.
            </p>
          </Subsection>
        </Section>

        <Section title="12. Indemnification">
          <p>
            You agree to indemnify and hold us harmless from any claims, damages, or expenses (including reasonable legal
            fees) arising from:
          </p>
          <ul className="list-disc pl-6 space-y-1">
            <li>Your use of the Service in violation of these Terms</li>
            <li>Your Content (including any claims that it infringes third-party rights)</li>
            <li>Your violation of any applicable law</li>
            <li>Your negligence or willful misconduct</li>
          </ul>
          <p>
            This obligation does not apply to the extent a claim arises from our own breach, negligence, or misconduct.
          </p>
        </Section>

        <Section title="13. Suspension and Termination">
          <Subsection title="13.1 Your Right to Terminate">
            <p>
              You may stop using the Service and delete your account at any time through the dashboard or by contacting{' '}
              <a href="mailto:support@rmirror.io" style={{ color: 'var(--terracotta)' }}>
                support@rmirror.io
              </a>
              . <strong>Account deletion is immediate and irreversible.</strong> Upon deletion, all Your Content
              (notebooks, OCR transcriptions, generated PDFs, and integration data) is permanently removed from our
              systems. We cannot recover deleted data. You are responsible for exporting any content you wish to keep{' '}
              <strong>before</strong> initiating account deletion.
            </p>
          </Subsection>

          <Subsection title="13.2 Our Right to Suspend or Terminate">
            <p>We may suspend or terminate your access to the Service if:</p>
            <ul className="list-disc pl-6 space-y-1">
              <li>You materially breach these Terms and fail to cure within <strong>14 days</strong> of notice</li>
              <li>You engage in conduct that threatens the security, integrity, or availability of the Service</li>
              <li>We are required to do so by law or court order</li>
              <li>
                Your account has been inactive for more than <strong>12 months</strong> (with 30 days&apos; prior notice)
              </li>
            </ul>
          </Subsection>

          <Subsection title="13.3 Effect of Termination">
            <p>
              <strong>If you delete your account (Section 13.1):</strong> Your data is deleted immediately and
              permanently as described in Section 13.1. No grace period applies.
            </p>
            <p>
              <strong>If we terminate or suspend your account (Section 13.2):</strong> You have{' '}
              <strong>30 days</strong> from the date of termination notice to export your data (via dashboard or by
              contacting support). After the 30-day grace period, we permanently delete your data from our systems.
            </p>
            <p><strong>In all cases:</strong></p>
            <ul className="list-disc pl-6 space-y-1">
              <li>Your right to use the Service ceases immediately upon termination</li>
              <li>Any outstanding payment obligations survive termination</li>
              <li>
                Sections 5.1 (Ownership), 8.3 (Feedback), 10 (Disclaimers), 11 (Liability), 12 (Indemnification), and
                15 (Governing Law) survive termination
              </li>
            </ul>
          </Subsection>

          <Subsection title="13.4 Service Discontinuation">
            <p>
              If we decide to discontinue the Service entirely, we will provide at least{' '}
              <strong>60 days&apos; advance notice</strong> via email and in the dashboard, along with the opportunity to
              export your data.
            </p>
          </Subsection>
        </Section>

        <Section title="14. Changes to These Terms">
          <Subsection title="14.1 Updates">
            <p>
              We may update these Terms from time to time. We will notify you of material changes:
            </p>
            <ul className="list-disc pl-6 space-y-1">
              <li>By email at least <strong>30 days</strong> before the changes take effect</li>
              <li>By a prominent notice in the dashboard</li>
            </ul>
          </Subsection>

          <Subsection title="14.2 Acceptance">
            <p>
              Your continued use of the Service after the effective date of updated Terms constitutes acceptance. If you
              disagree with the changes, you may terminate your account before the changes take effect.
            </p>
          </Subsection>

          <Subsection title="14.3 Legal Requirements">
            <p>
              Where changes are required by law or regulatory authority, we may implement them immediately without
              advance notice, with notification provided as soon as practicable.
            </p>
          </Subsection>
        </Section>

        <Section title="15. Governing Law and Dispute Resolution">
          <Subsection title="15.1 Governing Law">
            <p>
              These Terms are governed by the laws of <strong>Switzerland</strong>, without regard to conflict of law
              principles.
            </p>
          </Subsection>

          <Subsection title="15.2 Dispute Resolution">
            <p>Any disputes arising from these Terms shall be resolved as follows:</p>
            <ol className="list-decimal pl-6 space-y-1">
              <li><strong>Good-faith negotiation</strong> between the parties (30 days)</li>
              <li><strong>Mediation</strong> by the Swiss Chambers&apos; Arbitration Institution (30 days)</li>
              <li><strong>Competent courts of Zurich, Switzerland</strong> shall have exclusive jurisdiction</li>
            </ol>
          </Subsection>

          <Subsection title="15.3 EU Consumer Rights">
            <p>
              If you are a consumer in the EU, nothing in this section deprives you of the protection of mandatory
              provisions of the law of your country of residence, nor of your right to bring proceedings before the
              courts of your country of residence.
            </p>
          </Subsection>

          <Subsection title="15.4 Online Dispute Resolution">
            <p>
              EU consumers may also use the EU Online Dispute Resolution platform at:{' '}
              <a
                href="https://ec.europa.eu/consumers/odr/"
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: 'var(--terracotta)' }}
              >
                https://ec.europa.eu/consumers/odr/
              </a>
            </p>
          </Subsection>
        </Section>

        <Section title="16. Miscellaneous">
          <Subsection title="16.1 Entire Agreement">
            <p>
              These Terms, together with the Privacy Policy and Data Processing Agreement, constitute the entire
              agreement between you and us regarding the Service.
            </p>
          </Subsection>

          <Subsection title="16.2 Severability">
            <p>
              If any provision of these Terms is held invalid or unenforceable, the remaining provisions remain in full
              force. The invalid provision shall be modified to the minimum extent necessary to make it valid.
            </p>
          </Subsection>

          <Subsection title="16.3 No Waiver">
            <p>
              Our failure to enforce any provision of these Terms does not constitute a waiver of that provision or of
              our right to enforce it later.
            </p>
          </Subsection>

          <Subsection title="16.4 Assignment">
            <p>
              You may not assign your rights or obligations under these Terms without our prior written consent. We may
              assign our rights and obligations to a successor entity in connection with a merger, acquisition, or sale
              of all or substantially all of our assets, provided the successor assumes all obligations under these
              Terms.
            </p>
          </Subsection>

          <Subsection title="16.5 Force Majeure">
            <p>
              Neither party is liable for failure or delay caused by circumstances beyond reasonable control, including
              natural disasters, war, government actions, pandemics, or widespread internet outages. Payment obligations
              are not excused by force majeure.
            </p>
          </Subsection>

          <Subsection title="16.6 Notices">
            <p>
              Notices to us should be sent to:{' '}
              <a href="mailto:support@rmirror.io" style={{ color: 'var(--terracotta)' }}>
                support@rmirror.io
              </a>
            </p>
            <p>Notices to you will be sent to the email address associated with your account.</p>
          </Subsection>

          <Subsection title="16.7 Language">
            <p>
              These Terms are drafted in English. If translated, the English version prevails in case of conflict.
            </p>
          </Subsection>
        </Section>

        <Section title="17. Contact Information">
          <p>
            <strong>rMirror Cloud</strong>
            <br />
            Switzerland
            <br />
            Email:{' '}
            <a href="mailto:support@rmirror.io" style={{ color: 'var(--terracotta)' }}>
              support@rmirror.io
            </a>
            <br />
            Privacy inquiries:{' '}
            <a href="mailto:privacy@rmirror.io" style={{ color: 'var(--terracotta)' }}>
              privacy@rmirror.io
            </a>
            <br />
            Security issues:{' '}
            <a href="mailto:security@rmirror.io" style={{ color: 'var(--terracotta)' }}>
              security@rmirror.io
            </a>
          </p>
        </Section>

        <hr className="my-8" style={{ borderColor: 'var(--border)' }} />

        <p>
          <strong>
            By creating an account or using rMirror Cloud, you acknowledge that you have read, understood, and agree to
            be bound by these Terms of Service.
          </strong>
        </p>

        <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>
          <strong>Document Version History:</strong>
          <br />
          v1.0 (February 20, 2026): Initial version
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
