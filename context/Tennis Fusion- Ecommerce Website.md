# Tennis Fusion- Ecommerce Website

A full-featured e-commerce web application for tennis equipment and accessories. Built with **.NET 9** and **Angular 20**.

## Features

- Product catalog with search, filtering (by brand/type), and sorting
- Shopping cart with Redis-backed persistence
- Secure checkout with Stripe payment integration
- User registration & authentication (ASP.NET Core Identity)
- Order management with real-time status updates via SignalR
- Responsive design with Angular Material

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | .NET 9, ASP.NET Core Web API, Entity Framework Core |
| Frontend | Angular 20, Angular Material, Tailwind CSS |
| Database | SQL Server (Docker), Redis (Docker) |
| Payments | Stripe (test mode) |
| Real-time | SignalR |
| Auth | ASP.NET Core Identity, Cookie Auth |

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [.NET SDK 9](https://dotnet.microsoft.com/en-us/download/dotnet/9.0)
- [Node.js](https://nodejs.org/) (^20.19.0 \|\| ^22.12.0 \|\| ^24.0.0) — optional, only if running Angular dev server
- [Stripe CLI](https://stripe.com/docs/stripe-cli) — optional, for webhook testing

## Quick Start

### 1. Clone & setup

```bash
git clone https://github.com/YOUR_USERNAME/TennisFusion.git
cd TennisFusion
dotnet restore
cd client && npm install && cd ..
```

### 2. Start infrastructure (SQL Server + Redis)

```bash
docker compose up -d
```

### 3. Apply migrations & seed data

```bash
cd API
dotnet run
```

The app seeds the database with sample products and an admin user on first run.

### 4. Open the app

Browse to **https://localhost:5001**

### 5. Login (seeded user)

- **Email:** `admin@test.com`
- **Password:** `Pa$$w0rd`

## Stripe Setup (for payments)

1. Create a [Stripe account](https://stripe.com)
2. Replace the keys in `API/appsettings.json` with your test keys:

```json
{
  "StripeSettings": {
    "PublishableKey": "pk_test_YOUR_KEY",
    "SecretKey": "sk_test_YOUR_KEY",
    "WhSecret": "whsec_YOUR_KEY"
  }
}
```

3. For webhook support, run the Stripe CLI:

```bash
stripe login
stripe listen --forward-to https://localhost:5001/api/payments/webhook -e payment_intent.succeeded
```

Use Stripe test card `4242 4242 4242 4242` for payments.

## Running in Development Mode

To run the Angular app separately with hot-reload:

```bash
# Terminal 1 — API
cd API
dotnet run

# Terminal 2 — Angular dev server
cd client
ng serve
```

The Angular dev server runs on **https://localhost:4200** and proxies API requests to the .NET backend.
