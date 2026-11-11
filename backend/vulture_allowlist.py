"""Vulture allowlist: names vulture reports as unused that are kept on purpose.

Run from backend/:  vulture   (paths and options are in pyproject.toml)

Vulture treats any use of a name anywhere as a use, so each entry below
silences that name everywhere. Before adding a name, check it really is
used (framework hook, response field, database column, test-only helper the
owner wants to keep) and put it in the matching section.
"""

from vulture.whitelist_utils import Whitelist

_ = Whitelist()

# Framework hooks called by FastAPI / Starlette / Pydantic, never by our code.
_.cls  # first argument of @classmethod validators
_.Config
_.dispatch  # BaseHTTPMiddleware.dispatch
_.from_attributes
_.model_config

# Interface methods of abstract base classes (SyncTarget, StorageBackend);
# implementations exist for every target/backend and tests call them.
_.check_duplicate
_.delete_item
_.file_exists
_.get_file_url

# Fields read by the framework, not by our code: SQLAlchemy columns,
# relationships and enum members, Pydantic request/response fields, settings
# read by validators, and dataclass fields set from parsed reMarkable files.
_.agent_connected
_.agent_downloaded
_.approved_at
_.author
_.auto_sync_enabled
_.beta_enrolled_at
_.bookmarked
_.CANCELED
_.CANCELLED
_.claimed_at
_.claimed_by
_.confidence_score
_.connected
_.connectors
_.corrected_text
_.created_time
_.credentials_encrypted
_.current_page
_.current_period_end
_.current_period_start
_.current_privacy_version
_.current_tos_version
_.deleted_notebook_uuids
_.details
_.EPUB
_.EXTRACT_HIGHLIGHTS
_.extraction_method
_.first_notebook_synced
_.first_ocr_completed
_.FIRST_SYNC_COMPLETED
_.FIRST_SYNC_STARTED
_.FOLDER
_.FOLDER_CONFIGURED
_.fuzzy_signature
_.hashed_password
_.highlighted_at
_.highlights
_.in_progress
_.input_data
_.is_beta
_.is_inbox_project
_.is_verified
_.last_active_at
_.last_edited_time
_.last_sync
_.last_sync_at
_.match_score
_.max_retries
_.modified_client
_.name_match
_.note
_.notebooks_processed
_.notion_connected
_.ocr_completed_at
_.ocr_error
_.OCR_PAGE
_.PAST_DUE
_.PDF
_.pending_notebooks
_.position_data
_.postgres_db
_.postgres_host
_.postgres_password
_.postgres_port
_.postgres_user
_.privacy_accepted
_.privacy_accepted_at
_.PROCESS_NOTEBOOK
_.processing_jobs
_.queue_name
_.reason
_.redirect_document_uuid
_.result_data
_.s3_files_deleted
_.score
_.source_table
_.source_type
_.stripe_customer_id
_.stripe_subscription_id
_.subscription_expires_at
_.sync_interval_minutes
_.SYNC_TO_SERVICE
_.synced
_.synced_count
_.todos_extracted
_.token_type
_.tos_accepted
_.tos_accepted_at
_.total_matched_pages
_.total_notebooks_synced
_.total_pages_synced
_.total_users
_.TRIALING
_.valid

# Kept on purpose although no production code calls them (used by tests,
# documented in CLAUDE.md, or planned features). Remove only with the owner.
_.add_database_properties  # Notion data source schema updates
_.consume_quota  # documented quota API; used by quota tests
_.generate_data_export  # in-memory variant of the streamed account export
_.generate_master_key  # helper for creating INTEGRATION_MASTER_KEY
_.get_next_sync_items  # sync-queue helper used by tests
_.is_enterprise_tier  # Subscription model properties (Stripe phase 2)
_.is_free_tier
_.is_pro_tier
_.JobType  # ProcessingJob model enum (model left in place, see audit report)
_.ocr_quota  # User model property
_.queue_page_sync  # sync-queue helpers used by tests
_.queue_todo_sync
_.rebuild_combined_pdf  # notebook PDF rebuild, used by tests
_.send_admin_alert  # email helpers with escaping/golden tests
_.send_sync_notification
_.update_quota_limit  # tier change helper for Stripe phase 2
