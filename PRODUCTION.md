# 🔒 Production Branch — Private

> ⚠️ This branch contains proprietary implementation details.
> Do NOT merge into `main` or push to a public repository.

## What's Here (Private Only)

### Secret Sauce
- Full anomaly detection with Mahalanobis distance upgrade path
- Regime detector with adaptive vol window auto-tuning
- Liquidity analyzer calibration parameters for real order books
- Kyle's Lambda calibration against real-world execution data

### Sensitive Configuration
- `config.production.yaml` — Production thresholds (tighter limits)
- Real exchange connectivity parameters
- Admin keys and reset credentials

### Deployment Infrastructure
- Docker compose for multi-service deployment
- Kubernetes manifests for horizontal scaling
- Prometheus metrics + Grafana dashboard configs
- CI/CD pipeline with risk regression tests

### Datasets (Not in Public)
- Full tick-level 1987 crash data (non-redistributable)
- 2008 financial crisis minute bars
- 2020 COVID flash crash data
- Internal execution quality reports

## Branch Policy
- `main` → Public showcase (README, architecture, partial implementation)
- `production` → Full implementation + infra (PRIVATE)
- All PRs to `production` require 2 approvals
