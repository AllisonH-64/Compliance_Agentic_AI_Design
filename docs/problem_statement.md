# Problem Statement

## Who has the problem

A compliance analyst or compliance manager at a mid-market company — one too small to afford the NAVEX/OneTrust-tier enterprise GRC platforms, but large enough that vendor spend, gifts, and vendor relationships happen faster than any small compliance team can manually review. Secondary stakeholders: the accounts-payable clerk who processes vendor payments, and the procurement lead who onboards new vendors — both of whom currently have no systematic gate stopping a risky transaction before it happens.

## What the problem actually is

Today, in a company without a tool like this, vendor spend gets approved by habit and memory, not by policy:

- An invoice above the approval threshold goes out with no on-file sign-off, because nobody's tracking thresholds transaction-by-transaction.
- A new vendor gets paid before anyone checks a sanctions list, because screening is a manual step someone has to remember to do.
- A vendor emails updated bank routing details, and the change gets applied without anyone calling to confirm it's really the vendor — this is how business-email-compromise payment fraud actually happens, and it's one of the most common and costly fraud vectors in real accounts-payable operations.
- A sales manager takes a government official to dinner without realizing that's a bribery-law trigger regardless of amount, because nobody flagged it at the moment of spend.
- A "vendor" is actually a part-time worker in all but name, and nobody notices until a labor dispute surfaces the misclassification.
- A requestor has an undisclosed personal relationship with a vendor, and it only comes out after the money has already moved.

None of these are exotic failures. They're what happens by default when policy enforcement depends on someone remembering to apply it, rather than being a gate the transaction has to pass through.

## Why it matters

Each failure mode above maps to a real cost: fraud losses that are often unrecoverable once paid, statutory liability (Barbados's Prevention of Corruption Act carries penalties up to BBD$1,500,000 or 15 years imprisonment on indictment; the Employment Rights Act creates real exposure for worker misclassification), and the reputational and audit cost of not being able to reconstruct *why* a transaction was allowed to proceed after the fact.

## What "solved" looks like

A transaction doesn't get to proceed on the strength of someone's memory. It goes through a deterministic gate that:

1. Evaluates the transaction against a versioned, cited rule (not a vague policy PDF nobody reads at the moment of spend).
2. Produces a clear, explainable decision: approved, blocked, needs more evidence, or needs a human's judgment call.
3. Routes the right people (procurement, legal, finance) automatically based on how serious the finding is.
4. Leaves a permanent, reconstructible record of what was decided, by what rule, and why — so a compliance program can prove it was actually being followed, not just that it existed on paper.

That's the actual product: not "a FastAPI app" or "a DynamoDB table" — a gate that stands between a vendor transaction and the money moving, staffed by rules where rules are enough and by a human where they aren't.

## What this repo is not trying to solve

It is not a general-purpose GRC platform, not a replacement for legal counsel, and not a claim that any of its internal thresholds are legally mandated (see `docs/mvp.md`'s "Regulatory Sourcing" section — thresholds are internal policy unless a rule explicitly cites a verified regulatory floor). It's scoped to one domain — vendor/procurement spend — deliberately, because a narrow tool that actually works beats a broad one that's a demo.
