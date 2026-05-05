# Conversational AI for Hong Kong’s Sustainable Mobility and Urban Living Services
## Hong Kong Electronics Project Competition 2026 (HKEPC 2026)

---

## Project Overview
This project is a conversational AI system built for Hong Kong's smart city public service scenarios, developed for the HKEPC 2026 theme *"Mastering Artificial Intelligence in the Sustainable Development of Smart Cities"*.

Against the backdrop of abundant yet fragmented digital public resources in Hong Kong, this system addresses the critical pain point of high access costs for citizens to obtain daily urban service information. It unifies scattered public services across multiple platforms into a single, user-friendly multilingual conversational interface, with native support for Simplified Chinese, Traditional Chinese, and English.

Leveraging **Retrieval-Augmented Generation (RAG)** as its core technical framework, the system maps unstructured natural language queries to Hong Kong's authoritative public open data (from data.gov.hk and official portals) stored in a dedicated vector database, delivering accurate, context-aware, and data-driven responses. It transforms fragmented open datasets into actionable, easy-to-access services, maximizing the value of existing public data infrastructure while supporting sustainable urban development in Hong Kong.

---

## Core Features
The system adopts a decoupled modular architecture, with 5 coordinated functional modules sharing a unified RAG retrieval framework and standardized service interface:
- **A&E Waiting Time Inquiry Module**: Real-time perception channel for emergency medical services, providing standardized, semantically aligned feedback on emergency triage categories and real-time waiting status of Hong Kong's public hospitals.
- **Clinic Quota Lookup Module**: Intelligent parsing system for outpatient service quotas, with targeted identification of medical service outlets, temporal extraction, and human-readable summarization of public outpatient appointment resources.
- **Food Licence Geospatial Query Module**: Geospatial query service for food business regulation, converting user-side spatial and attribute constraints into standardized query logic for accurate retrieval of legitimate food business entities.
- **Sustainability-oriented Hotel Recommendation Module**: Fusion recommendation system for accommodation services, integrating multi-source accommodation data and delivering intelligent sorting based on user preferences, spatiotemporal conditions, and Hong Kong's urban sustainable development guidelines.
- **Urban Environmental & Recycling Services Module**: Collaborative perception system for urban environmental resources, linking Hong Kong's recycling facility layout with atmospheric environment monitoring network to generate integrated natural language summaries of regional environmental services.

---

## Technical Architecture
The system is built on a modular, end-to-end architecture centered on a routing core and domain-specific handlers, with RAG as the core of the data retrieval layer. The core workflow is as follows:
1. **Hybrid Intent Analysis**: User queries first enter a hybrid intent-analysis stage, combining deterministic rule matching for high-priority keywords (e.g., emergency, clinic) with LLM-powered semantic parsing, ensuring robustness for noisy or mixed-language input.
2. **Entity Normalization & Request Routing**: After intent identification, the system normalizes extracted entities (e.g., hospital name, district, date) into executable parameters, and dispatches the request to the corresponding dedicated service module.
3. **RAG-Powered Knowledge Retrieval**: The normalized query is mapped to a high-dimensional latent vector space via a domain-optimized embedding model. The system calculates cosine similarity between the query vector and knowledge chunk vectors in the shared vector database, retrieving the top-k most relevant structured data from Hong Kong's official open data sources.
4. **Multilingual Response Synthesis**: Retrieved structured knowledge chunks are passed to the LLM-assisted response synthesis layer, which converts machine-readable data into concise, coherent, and semantically consistent multilingual natural language narratives.

---

## Quick Start
Follow the steps below to deploy and run the system locally:

### 1. Install Dependencies
Run the following command in your terminal to install required Python packages:
```bash
pip install -r requirements.txt
```

### 2. Start the Web Backend
Launch the backend service with the following command:
```bash
python web_app.py
```

### 3. Access the Web Interface
After the backend starts successfully, open your browser and navigate to the local service address:
http://127.0.0.1:5000/
