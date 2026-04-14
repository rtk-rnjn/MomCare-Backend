# MomCare Admin Dashboard

A production-grade interactive admin dashboard for the MomCare Backend application.

## Features

- **Admin Authentication**: JWT-based login with role hierarchy (super_admin / admin)
- **User Management**: List, search, filter, sort, paginate users; view details; lock/unlock/delete
- **Model Management**: CRUD operations for exercises, foods, and songs with bulk actions
- **Log Analytics**: Interactive charts for 2xx/3xx/4xx/5xx status codes with time range filters
- **Database Tools**: Redis CLI with safe command whitelist; MongoDB collection browser
- **System Controls**: Health checks, server restart (super-admin only, feature-flagged)
- **Audit Logging**: Every admin action is logged with who, what, target, timestamp, and metadata

## Environment Variables

Add these to your `.env` file (see `example.env` for reference):

| Variable | Required | Description |
|----------|----------|-------------|
| `ADMIN_USERNAME` | Yes | Bootstrap super admin username |
| `ADMIN_PASSWORD` | Yes | Bootstrap super admin password |
| `ADMIN_ENABLE_RESTART` | No | Enable server restart endpoint (default: `false`) |
| `JWT_SECRET_KEY` | Yes | JWT signing secret (shared with user auth) |
| `JWT_ALGORITHM` | Yes | JWT algorithm (e.g., `HS256`) |
| `MONGODB_URI` | Yes | MongoDB connection string |
| `SESSION_SECRET_KEY` | Yes | Session middleware secret |
| `REDIS_HOST` | No | Redis host (default: `localhost`) |
| `REDIS_PORT` | No | Redis port (default: `6379`) |
| `REDIS_PASSWORD` | No | Redis password |
| `REDIS_DB` | No | Redis database number (default: `5`) |

## Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment**:
   ```bash
   cp example.env .env
   # Edit .env with your values, especially ADMIN_USERNAME and ADMIN_PASSWORD
   ```

3. **Start the server**:
   ```bash
   python main.py
   ```
   The super admin is automatically created on first startup.

4. **Access the dashboard**:
   Navigate to `http://localhost:8080/admin-dashboard`

## API Endpoints

All admin endpoints are prefixed with `/api/admin/`.

### Authentication
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/admin/auth/login` | None | Admin login |
| POST | `/api/admin/auth/refresh` | None | Refresh tokens |
| POST | `/api/admin/auth/logout` | Admin | Logout |
| GET | `/api/admin/auth/me` | Admin | Get current admin |

### Admin Management (Super Admin Only)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/admins/` | List all admins |
| POST | `/api/admin/admins/` | Create new admin |
| GET | `/api/admin/admins/{id}` | Get admin by ID |
| PATCH | `/api/admin/admins/{id}` | Update admin |
| DELETE | `/api/admin/admins/{id}` | Delete admin |

### User Management
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/users/` | List users (search, filter, sort, paginate) |
| GET | `/api/admin/users/{id}` | Get user details |
| POST | `/api/admin/users/{id}/lock` | Lock user |
| POST | `/api/admin/users/{id}/unlock` | Unlock user |
| DELETE | `/api/admin/users/{id}` | Soft-delete user |

### Model Management
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/models/{collection}` | List items |
| GET | `/api/admin/models/{collection}/{id}` | Get item |
| POST | `/api/admin/models/{collection}` | Create item |
| PUT | `/api/admin/models/{collection}/{id}` | Update item |
| DELETE | `/api/admin/models/{collection}/{id}` | Delete item |
| POST | `/api/admin/models/{collection}/bulk-delete` | Bulk delete |

Collections: `exercises`, `foods`, `songs`

### Log Analytics
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/logs/analytics` | Status code analytics |
| GET | `/api/admin/logs/timeline` | Request timeline |
| GET | `/api/admin/logs/errors` | Error log viewer |
| GET | `/api/admin/logs/drilldown` | Filterable log drilldown |
| GET | `/api/admin/logs/audit` | Audit log viewer |

### Database Tools
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/admin/db/redis/execute` | Execute Redis command |
| GET | `/api/admin/db/redis/allowed-commands` | List allowed commands |
| GET | `/api/admin/db/redis/info` | Redis server info |
| GET | `/api/admin/db/mongo/collections` | List MongoDB collections |
| GET | `/api/admin/db/mongo/collections/{name}` | Browse collection |
| GET | `/api/admin/db/mongo/collections/{name}/{id}` | Get document |
| DELETE | `/api/admin/db/mongo/collections/{name}/{id}` | Delete document |
| GET | `/api/admin/db/mongo/stats` | MongoDB stats |

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/system/dashboard` | Dashboard overview |
| GET | `/api/admin/system/health` | Health checks |
| POST | `/api/admin/system/restart` | Restart server (super admin only) |

## Security

### Role Hierarchy
- **Super Admin**: Full access. Created from env vars on first startup. Cannot be deleted or modified through the API.
- **Admin**: Access to user management, model management, logs, and DB tools. Cannot manage other admins or restart the server.

### Security Measures
- All admin routes require JWT authentication via `Authorization: Bearer <token>`
- Access tokens expire after 2 hours; refresh tokens after 24 hours
- Password hashing uses bcrypt with automatic salting
- Redis CLI tool has a strict whitelist of allowed commands and blocks dangerous operations
- MongoDB tool prevents deletion from `admin_users` and `audit_logs` collections
- Server restart is gated by `ADMIN_ENABLE_RESTART` feature flag and requires super admin role
- Every privileged action is logged to the audit trail

### Safe Defaults
- Restart is disabled by default (`ADMIN_ENABLE_RESTART=false`)
- Redis commands like `FLUSHDB`, `FLUSHALL`, `SHUTDOWN`, `CONFIG` are explicitly forbidden
- Admin cannot escalate their own privileges
- Super admin account is unique and cannot be duplicated

## Testing

Run the admin tests:
```bash
cd /path/to/MomCare-Backend
python -m pytest tests/admin/test_admin.py -v
```

The test suite covers:
- Password hashing and verification
- JWT token creation and validation
- Admin model validation (input constraints)
- RBAC role checks (super_admin vs admin)
- Restart authorization logic
- Feature flag behavior
- Audit log and HTTP log model validation

## Architecture

```
src/
├── models/
│   ├── admin.py          # Admin user model and schemas
│   ├── audit_log.py      # Audit log model
│   └── http_log.py       # HTTP request log model
├── utils/
│   ├── admin_auth.py     # Admin JWT auth, RBAC dependencies
│   └── audit_logger.py   # Audit logging utility
├── routes/
│   ├── api/admin/
│   │   ├── __init__.py   # Admin router aggregation
│   │   ├── auth.py       # Login/logout/refresh/me
│   │   ├── manage.py     # Admin CRUD (super admin)
│   │   ├── users.py      # User management
│   │   ├── models.py     # Model CRUD
│   │   ├── logs.py       # Log analytics and audit
│   │   ├── db_tools.py   # Redis CLI and MongoDB browser
│   │   └── system.py     # Dashboard, health, restart
│   └── web/admin/
│       └── __init__.py   # Admin dashboard SPA
├── middleware/
│   └── logger.py         # Enhanced with MongoDB log storage
└── lifespan.py           # Enhanced with super admin bootstrap
```

## Frontend

The admin dashboard is served as a single-page application at `/admin-dashboard`. It uses:
- React 18 (via CDN)
- Tailwind CSS (via CDN)
- Chart.js for analytics visualization
- Hash-based routing for SPA navigation

All data is fetched from the `/api/admin/` endpoints.
