So we're going to build an AI news aggregator, right? I still have no idea what this is going to look like, but but

I have a general idea of how I like to build things.

Let's start brainstorming. So what I want to build is an AI news aggregator where I can take multiple sources. So

for example, YouTube channels and I want for example blog posts from OpenAI and

Athropic and other sources and I want to scrape those put them into a database where we have some

kind of structure where we have sources we have let's call them articles and then what I want to do is I want to run

a daily digest where we're going to take all of the articles from within that

time frame and we're going to do an LLM summary around that and then based on the user insights that we specify in

some kind of agent system prompt. We can generate a daily digest which is going to be short

snippets with a link to the original source. Now from the YouTube channels I want to be able to create a list of channels and then we want to get the latest videos from those channels. I think we can use the YouTube RSS feed for that and for for the blog posts we can just have URLs that we can scrape for that. Okay. So I want everything built in a Python back end. I want to use a Postgress SQL database supabase in this case. I want to use SQL alchemy in order to define the database models and then to also create the tables.

I want to have a backend and frontend.


### Backend
The backend will consist of AWS lambda definitions, AWS ECS Express Mode, apigateway, apigateway, and database configurations

1. scraper
- An application to deploy to AWS ECS with Express Mode (Apprunner is being deprecated by AWS)
- Scrapes the youtube rss feeds from the different youtube channels and sends results to supabase. See config sources yaml file and youtube rss pipeline
- Scrapes the rss feeds from the different rss feed urls and send to supabase. See the rss parser pipeline
- Has an agent (OpenAI Agents SDK) using the playwright mcp server to do web search on the internet and scrape AI related content from different sources (OpenAI, Anthropic, everything AI and LLMs etc) with structured outputs and Sends to supabase.
- Handoff to the Digest Agent

2. Digest Agent (In Lambda function).
- An agent (OpenAI agent SDK) that generates summaries of the recently added articles (Youtube video transcriptions, rss feeds entries, blog articles etc) with structured output andthen sending summary to supabase table

3. Editor Agent (In Lambda Function)

AI Editor Agent (OpenAI Agents SDK) for curating and ranking news digests.

This agent acts like a news editor, analyzing digest articles and ranking them
based on a user's profile, interests, and preferences. Uses OpenAI's Responses API
with structured output for type-safe, consistent ranking results.

4. Email Agent(In Lambda function)

AI Email Agent (OpenAI Agents SDK) for generating personalized email digest introductions.

This agent creates engaging, personalized email introductions based on:
- User profile (name, interests)
- Top ranked articles
- Current date
- Key themes from the articles

5. A scheduler (Lambda function)

Lambda function to trigger scraper (AWS ECS with Express Mode) endpoint. Called by EventBridge on a schedule (Everyday at Midnight).

6. Database

A package with;
- Client module for setting up and connecting to supabase
- Modules for database models with methods for low level business logic and schemas (pydantic models)
- Running migrations and reseting a database

7. Guardrails
- Audit logging for AI decisions.
- Tenacity-based retry for agent Lambda invocations.
- Input sanitization against prompt-injection patterns.
- Response size cap to prevent runaway token usage.
- Structured output validators for agent responses.

8. API
- Lambda handler for the FastAPI application."
- FastAPI backend for AI News Aggregator
- Handles all API routes with Clerk JWT authentication (We shall the Clerk Authentication integration with supabase. Use Context7 here for the supabase clerk auth documentation)


All deployments should be done using terraform and bash scripts. Use this repository to see the folder structure and deployment organisations I want to mimic https://github.com/PatrickCmd/alex-multi-agent-saas.
Backend we should use uv for package library dependency management.

### Frontend
- I need to have a frontend UI (Nextjs React Typescript) where users should be able to signup and signin using clerk (Use Context7 for supabase clerk auth with nexttjs and backend python).
- When users signup/in we need them to provide their profiles, use @config/user_profile.yml as reference
- They should see also their digests as according to their profiles
- Able to trigger a digest at any given moment, this should show on the UI and a respective email sent to them.
- Deployment is done to AWS S3 with static web hosting and served via cloudfront distributin attached to a custom domain. I already have an existing Route53 with primary domain and ace certificates, only just need to create a subdomain for my web UI.
- Deployment by terraform and bash scripts

We shall Use Context7 for any library up-to-date documentation.
