# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Delegated by the user: React frontend, Python API and SQLite, selected for the existing 2 vCPU / 4 GB Ubuntu VPS. The user chose image mockups before frontend implementation.

## Users

The owner creates and distributes personal VPN subscription links. Recipients open a link on a phone or computer and import it into Happ or a v2Ray client.

## Product Purpose

A small, attractive server-hosted landing page and administration panel for issuing, inspecting and disabling VPN access links.

## Operating Context

The VPS is 217.60.19.243, hostname mainvps, Ubuntu 26.04. An existing NaiveProxy service occupies HTTPS port 443 and is used by the owner's computer. The user explicitly chose the IP address for initial hosting rather than supplying a domain. All persistent production data belongs on this server.

## Capabilities and Constraints

Personal subscription links compatible with Happ and v2Ray. Owner-only administration. Traffic usage, expiry, quota and enabled state. A compatible VLESS endpoint will coexist with NaiveProxy. Working NaiveProxy access must survive deployment. No payments, public signup, invented performance claims or surveillance of browsing destinations are requested.

## Evidence on Hand

Existing server access, valid public IP TLS certificate and tested NaiveProxy profiles. No supplied logo, photos, customer counts or testimonials. Working product name "Линия" is an implementation assumption, not a confirmed brand commitment.

## Product Principles

- A recipient receives one durable personal link.
- Limits and revocation affect real VPN access.
- Metrics reflect measured usage and clearly distinguish link opens from VPN activity.
- Phone setup should require as few steps as the client allows.

## Recipient sign-in

Recipients sign into `/account` using an owner-issued username and password, with optional 30-day remembered sessions. Credentials are created in the admin access form, can be generated or customized, and can be reset for legacy or existing access. Passwords are stored as salted scrypt hashes and shown to the owner once in the issuance/reset response; regular API reads never expose them. User and owner sessions are separate. Tariff stops remain inspectable; archival removes account access. Existing bearer subscription/invitation links remain compatible.

Recipients may change their own password after providing the current password and confirming a new one. The current session rotates without extending its original lifetime; other sessions are revoked. Bearer-link entry alone cannot change credentials. VPN access conditions and subscription keys remain unchanged.
