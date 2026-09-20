# Repository

This repo organizes OpenCode telemetry into transcripts that can be searched.

Roughly sketched out

(a) An OpenCode plugin for logging raw telemetry (for OpenCode 1.18)
(b) Python code to turn it into documents to be searched
(c) A daemon service that indexes / searches
(d) CLIs that interact with the daemon to search, etc on behalf of agents

The javascript OpenCoded plugin should be extremely lightweight with minimal complexity. It should log user mesasge ID, sessionID, and as much raw data to help us group memories tied to a user prompt and 

The meat of the project is the Python code that indexes specific memories / artifacts, and then surfaces them in a CLI.

## Turbopuffer

Be sure when asked about Turbopuffer to search the latest documentation, as the project evolves fast, and your knowledge may be out of date.
