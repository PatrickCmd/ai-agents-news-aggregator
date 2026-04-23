# AI News Aggregator

A simple and efficient news aggregator for AI-related content from multiple sources including YouTube channels, OpenAI blog, Anthropic blog etc.

## Features

- **YouTube RSS Scraping**: Automatically fetch latest videos from configured channels with transcript extraction
- **Blog Post Scraping**: Scrape AI-related blog posts from OpenAI, Anthropic, and other sources, see @rss_feeds.md
- **AI-Powered Digest Generation**: Automatically generate concise 2-3 sentence summaries using OpenAI's GPT-5.4-mini
- **Intelligent Content Processing**: AI agent creates engaging titles and summaries for all articles
- **Editor Agent Ranking**: AI-powered curation that ranks articles (0-100) based on your personal interests and profile
- **A Web Search Agent**: Searching the web for AI related content from multiple sources using the playwright mcp server
- **Customizable User Profiles**: YAML-based profiles to tailor article ranking to your specific needs
- **Personalized Email Digests**: Beautiful HTML emails with AI-generated introductions, color-coded scores, and curated top articles
- **Email Agent**: Generates warm, personalized email introductions using your name and interests
- **Development & Production Modes**: Preview emails locally or send email via Rescend (Gmail, etc.)
- **Scheduled Execution**: Automated daily scraping and digest generation
- **PostgreSQL Storage**: Robust data storage with supabase
- **Production Deployment**: Deployment to AWS lambda, ECS express mode, apigateway, cloudfront, and scheduled jobs