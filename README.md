# StartupNews

This repository contains **StartupNews**, a full-stack blog platform with a **Raft-based gRPC back-end** and a **React front-end**.  
It is designed to stay online even if some replicas crash, and it ships with a local mail queue for development e-mails.

---

## Features

- **Accounts & Authentication**

  - Secure salted hashing for writer passwords
  - Prevents the same user from logging in on multiple devices simultaneously

- **n-Fault-Tolerant Storage**

  - As long as **> 50 %** of replicas are alive, reads & writes succeed
  - New replicas can be added or removed on the fly

- **E-mail Notifications**

  - Subscribers receive e-mails on new posts
  - Local dev uses MailHog; production can use Gmail SMTP

- **Horizontal Scaling**
  - `replicas.json` lets you start as many Raft nodes as you need
  - `start_servers.py --all` spins them up in parallel

---

## Setup

### Clone & install

```
git clone https://github.com/your-org/StartupNews.git
cd StartupNews
# back-end deps
cd startup-news-backend
pip install -r requirements.txt

# CLI helpers (macOS)
brew install uvicorn           # serves the FastAPI bridge
brew install mailhog           # fake SMTP inbox
brew services run mailhog      # UI → http://localhost:8025
brew install redis
brew services run redis        # For the distributed email queue

```

We also need to allow for environmental variables. An example is as follows

```
cp .env.example .env
# HOST=localhost
# PORT="65432"
# SMTP_SERVER=smtp.gmail.com
# SMTP_PORT=587
# SMTP_USERNAME=something@gmail.com
# SMTP_PASSWORD=abcd efgh ijkl mnop # optional – only for real e-mail
# default_sender=something@gmail.com
# use_tls=True
# REDIS_HOST=localhost
# REDIS_PORT=6379
# REDIS_PASSWORD=
# REDIS_DB=0
```

To start replicas, we can use

```
# kill any stray replicas from old runs
pkill -f "python.*server.py" || true

# boot every replica listed in replicas.json
python start_servers.py --all
```

We also need to start the rest bridge between React and gRPC. To do this, look at your computer's port, and run

```
uvicorn rest_bridge:app --reload --host [computer port]
```

You should now have terminals open for your servers, a terminal open for the rest bridge, and a terminal open to run mailhog. Now, all that's left is to run the frontend. We can do that with

```
cd startup-news
npm run dev
```

to activate the frontend

## Architecture of the Back-End

| Layer                | File(s)                          | Purpose                                 |
| -------------------- | -------------------------------- | --------------------------------------- |
| **gRPC API**         | `server.py`, `protos/blog.proto` | Business logic + Raft replication       |
| **Raft Core**        | `consensus.py`                   | Log entries, persistent term/vote state |
| **Replica Launcher** | `start_servers.py`               | Spawns multiple `server.py` instances   |
| **REST Bridge**      | `rest_bridge.py`                 | FastAPI façade for the React UI         |
| **E-mail Queue**     | `email_queue.py`                 | Background worker, MailHog in dev       |
| **Utilities**        | `util.py`, `writer.py`, etc.     | Hashing, helper classes                 |
| **Tests**            | `tests/*.py`                     | Unit & integration tests                |

### Consensus Protocol

We implement the **Raft Consensus Algorithm** for leader election and log replication:

1. **Leader election** – followers start an election if heartbeats stop.
2. **Log replication** – leader appends entries, replicates to followers, commits after majority ack.
3. **State machine** – committed entries are applied in order for strict consistency.
4. **Safety** – term, vote, and log are persisted so crashed replicas recover without data loss.

### Persistent Storage

| Data                                            | Format        | File                                     |
| ----------------------------------------------- | ------------- | ---------------------------------------- |
| Raft state (`currentTerm`, `votedFor`, `log[]`) | JSON          | `<replica>.raft.json`                    |
| Blog data (users, posts, comments)              | CSV snapshots | `users.csv`, `posts.csv`, `comments.csv` |

### Protocol Bridge

The browser speaks **REST/JSON** → `rest_bridge.py` → **gRPC** → `server.py`, shielding the UI from gRPC details and simplifying CORS.

## Unit Tests

Run tests per the unit tests file.

```
python test.py
```

### Helpful Commands

| Action                    | Command                                                                                     |
| ------------------------- | ------------------------------------------------------------------------------------------- |
| **Start all replicas**    | `python start_servers.py --all`                                                             |
| **Kill running replicas** | `pkill -f "python.*server.py" \|\| true`                                                    |
| **Add a replica**         | Edit `replicas.json`, then call gRPC `RPCAddReplica`                                        |
| **Regenerate gRPC stubs** | `python -m grpc_tools.protoc -Iprotos --python_out=. --grpc_python_out=. protos/blog.proto` |

### Notes

To run the app fully, everywhere in the code where you put in your own host, e.g. localhost or something like 10.2...., you should replace it everywhere with the host of your own choosing, both in the backend and the frontend. Right now, the code is configured to our hosts.
