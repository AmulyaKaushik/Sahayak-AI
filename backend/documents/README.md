# Policy PDFs for the RAG pipeline

Drop the PDFs here, then run (from `backend/`):

    python -m rag.folder_sync

(or call `POST /api/v1/admin/documents/sync` with the `X-Admin-Key` header).

**Which folder a PDF goes in decides which scheme its answers belong to:**

    documents/
      home_loan/loan_policy.pdf          -> scheme_id "home_loan"
      kisan_credit_card/kcc_guide.pdf    -> scheme_id "kisan_credit_card"
      general_banking_faq.pdf            -> no scheme (searched for every scheme)

Valid folder names: sukanya_samriddhi, pm_jan_dhan_yojana,
pmay_rural_housing_subsidy, kisan_credit_card, retail_micro_loan,
senior_citizen_savings_scheme, pm_mudra_yojana_shishu, home_loan,
atal_pension_yojana.

Rules:
- Text PDFs only. Scanned PDFs are reported as `needs_ocr` and skipped.
- Already-ingested files (same content) are skipped, so running the sync
  again is safe. Moving a file into a scheme folder re-tags it (no re-embedding).
- A changed file is ingested as a new document. The old version stays
  searchable until you remove it from the database.
