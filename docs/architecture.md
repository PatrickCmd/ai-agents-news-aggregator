# Architecture

Mermaid diagrams of the AI News Aggregator's full target system. The authoritative design spec lives at [docs/superpowers/specs/2026-04-23-foundation-design.md](superpowers/specs/2026-04-23-foundation-design.md). Only Sub-project #0 (Foundation) is implemented today.

## Full system

```mermaid
flowchart TB
    subgraph EXT[External Sources]
        YT[YouTube RSS]
        RSS[RSS Feeds<br/>OpenAI · Anthropic · AWS · ...]
        WEB[Web Pages]
    end

    subgraph SCHED[AWS EventBridge]
        CRON[Daily cron<br/>00:00 UTC]
    end

    subgraph ECSBOX[AWS ECS Express Mode]
        SCRAPER[Scraper Service · FastAPI]
        YTP[YouTube Pipeline]
        RSSP[RSS Pipeline<br/>via rss-mcp]
        WSA[Web Search Agent<br/>Playwright MCP]
    end

    subgraph LAM[AWS Lambda]
        DIGEST[Digest Agent<br/>per-article summaries]
        EDITOR[Editor Agent<br/>rank top 10 per user]
        EMAILAG[Email Agent<br/>intro + Resend send]
        API[FastAPI · API Gateway<br/>Clerk JWT]
    end

    subgraph SUPA[Supabase · Postgres]
        ARTICLES[(articles)]
        USERS[(users)]
        DIGESTS[(digests)]
        EMAILS[(email_sends)]
        AUDIT[(audit_logs)]
    end

    subgraph CLIENTS[Clients]
        FE[Next.js Frontend<br/>Clerk Sign-in<br/>S3 + CloudFront]
        INBOX[User Inbox]
    end

    subgraph OBS[Observability]
        LF[Langfuse]
        OAI[OpenAI Traces]
        CW[CloudWatch Logs]
    end

    YT --> YTP
    RSS --> RSSP
    WEB --> WSA

    CRON --> SCRAPER
    SCRAPER --> YTP
    SCRAPER --> RSSP
    SCRAPER --> WSA
    YTP --> ARTICLES
    RSSP --> ARTICLES
    WSA --> ARTICLES

    SCRAPER -- handoff --> DIGEST
    DIGEST --> ARTICLES
    DIGEST -- handoff per user --> EDITOR
    EDITOR --> USERS
    EDITOR --> ARTICLES
    EDITOR --> DIGESTS
    EDITOR -- handoff --> EMAILAG
    EMAILAG --> DIGESTS
    EMAILAG --> EMAILS
    EMAILAG --> INBOX

    FE -- API Gateway + Clerk JWT --> API
    API --> USERS
    API --> DIGESTS
    API -- on-demand trigger --> DIGEST

    WSA -. trace .-> LF
    WSA -. trace .-> OAI
    DIGEST -. trace .-> LF
    DIGEST -. trace .-> OAI
    EDITOR -. trace .-> LF
    EDITOR -. trace .-> OAI
    EMAILAG -. trace .-> LF
    EMAILAG -. trace .-> OAI

    SCRAPER -. audit .-> AUDIT
    DIGEST -. audit .-> AUDIT
    EDITOR -. audit .-> AUDIT
    EMAILAG -. audit .-> AUDIT

    SCRAPER -. logs .-> CW
    DIGEST -. logs .-> CW
    EDITOR -. logs .-> CW
    EMAILAG -. logs .-> CW
    API -. logs .-> CW
```

## Sub-project dependency graph

```mermaid
flowchart LR
    subgraph S0[#0 Foundation · SHIPPED]
        PKG[packages/* · schemas · db · config · observability]
    end
    subgraph S1[#1 Ingestion]
        ECSX[services/scraper]
    end
    subgraph S2[#2 Agents]
        AG[services/agents · digest · editor · email]
    end
    subgraph S3[#3 Orchestration]
        SCHX[EventBridge · handoff wiring]
    end
    subgraph S4[#4 API + Auth]
        APX[services/api + Clerk]
    end
    subgraph S5[#5 Frontend]
        WEBX[web/ Next.js]
    end
    subgraph S6[#6 Infra]
        IAC[Terraform + CI/CD]
    end
    S0 --> S1 --> S2 --> S3
    S0 --> S4 --> S5
    S1 --> S6
    S2 --> S6
    S3 --> S6
    S4 --> S6
    S5 --> S6
```
