#!/usr/bin/env python3
"""
MomCare Admin CLI - Command-line utilities for admin management.

Usage:
    python cli.py create-admin
    python cli.py rotate-password <username>
    python cli.py deactivate-admin <username>
    python cli.py activate-admin <username>
    python cli.py clear-user-locks
    python cli.py clear-user-lock <user_id>
    python cli.py export-audit-log [--output FILE] [--limit N]
    python cli.py export-login-attempts [--output FILE] [--limit N]
    python cli.py list-admins
"""
from __future__ import annotations

import asyncio
import csv
import getpass
import json
import os
import sys
import uuid
from datetime import datetime

import bcrypt
from dotenv import load_dotenv

load_dotenv()


async def _get_db():
    from pymongo.asynchronous.mongo_client import AsyncMongoClient

    uri = os.environ["MONGODB_URI"]
    client = AsyncMongoClient(uri, tz_aware=True)
    db = client["MomCare"]
    return client, db


async def _create_admin():
    print("=== Create Admin Account ===")
    username = input("Username: ").strip()
    if len(username) < 3:
        print("Error: Username must be at least 3 characters.")
        return

    display_name = input("Display name: ").strip()
    if not display_name:
        display_name = username

    password = getpass.getpass("Password (min 8 chars): ")
    if len(password) < 8:
        print("Error: Password must be at least 8 characters.")
        return

    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Error: Passwords do not match.")
        return

    print("Role options: super_admin, operator")
    role = input("Role [operator]: ").strip().lower() or "operator"
    if role not in ("super_admin", "operator"):
        print(f"Error: Invalid role '{role}'. Choose 'super_admin' or 'operator'.")
        return

    client, db = await _get_db()
    try:
        existing = await db["admin_users"].find_one({"username": username})
        if existing:
            print(f"Error: Admin '{username}' already exists.")
            return

        import arrow

        now = arrow.utcnow().timestamp()
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        admin = {
            "_id": str(uuid.uuid4()),
            "username": username,
            "display_name": display_name,
            "password_hash": password_hash,
            "role": role,
            "created_at_timestamp": now,
            "updated_at_timestamp": now,
            "last_login_timestamp": None,
            "is_active": True,
            "allowed_ips": [],
        }
        await db["admin_users"].insert_one(admin)
        print(f"✓ Admin '{username}' (role: {role}) created successfully.")
    finally:
        await client.close()


async def _rotate_password(username: str):
    print(f"=== Rotate Password for '{username}' ===")
    password = getpass.getpass("New password (min 8 chars): ")
    if len(password) < 8:
        print("Error: Password must be at least 8 characters.")
        return

    confirm = getpass.getpass("Confirm new password: ")
    if password != confirm:
        print("Error: Passwords do not match.")
        return

    client, db = await _get_db()
    try:
        import arrow

        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        result = await db["admin_users"].update_one(
            {"username": username},
            {"$set": {"password_hash": password_hash, "updated_at_timestamp": arrow.utcnow().timestamp()}},
        )
        if result.matched_count == 0:
            print(f"Error: Admin '{username}' not found.")
        else:
            print(f"✓ Password for '{username}' rotated successfully.")
    finally:
        await client.close()


async def _deactivate_admin(username: str):
    client, db = await _get_db()
    try:
        import arrow

        result = await db["admin_users"].update_one(
            {"username": username},
            {"$set": {"is_active": False, "updated_at_timestamp": arrow.utcnow().timestamp()}},
        )
        if result.matched_count == 0:
            print(f"Error: Admin '{username}' not found.")
        else:
            print(f"✓ Admin '{username}' deactivated.")
    finally:
        await client.close()


async def _activate_admin(username: str):
    client, db = await _get_db()
    try:
        import arrow

        result = await db["admin_users"].update_one(
            {"username": username},
            {"$set": {"is_active": True, "updated_at_timestamp": arrow.utcnow().timestamp()}},
        )
        if result.matched_count == 0:
            print(f"Error: Admin '{username}' not found.")
        else:
            print(f"✓ Admin '{username}' activated.")
    finally:
        await client.close()


async def _clear_user_locks(user_id: str | None = None):
    client, db = await _get_db()
    try:
        import arrow

        filter_q: dict = {"account_status": "locked"}
        if user_id:
            filter_q["_id"] = user_id

        result = await db["credentials"].update_many(
            filter_q,
            {
                "$set": {
                    "account_status": "active",
                    "failed_login_attempts": 0,
                    "failed_login_attempts_timestamp": None,
                    "locked_until_timestamp": None,
                    "updated_at_timestamp": arrow.utcnow().timestamp(),
                }
            },
        )
        if user_id:
            print(f"✓ Cleared lock for user '{user_id}'. Modified: {result.modified_count}")
        else:
            print(f"✓ Cleared all user locks. Modified: {result.modified_count}")
    finally:
        await client.close()


async def _export_audit_log(output_file: str | None = None, limit: int = 1000):
    client, db = await _get_db()
    try:
        cursor = db["admin_audit_log"].find({}).sort("timestamp", -1).limit(limit)
        logs = await cursor.to_list(length=limit)

        if output_file:
            with open(output_file, "w", newline="", encoding="utf-8") as f:
                if output_file.endswith(".csv"):
                    writer = csv.DictWriter(f, fieldnames=["_id", "admin_username", "action", "resource_type",
                                                           "resource_id", "ip_address", "timestamp", "details"])
                    writer.writeheader()
                    for log in logs:
                        writer.writerow({
                            "_id": log.get("_id", ""),
                            "admin_username": log.get("admin_username", ""),
                            "action": log.get("action", ""),
                            "resource_type": log.get("resource_type", ""),
                            "resource_id": log.get("resource_id", ""),
                            "ip_address": log.get("ip_address", ""),
                            "timestamp": datetime.fromtimestamp(log.get("timestamp", 0)).isoformat(),
                            "details": log.get("details", ""),
                        })
                else:
                    json.dump([{k: v for k, v in log.items() if k != "_id" or True} for log in logs],
                              f, indent=2, default=str)
            print(f"✓ Exported {len(logs)} audit log entries to '{output_file}'.")
        else:
            for log in logs:
                ts = datetime.fromtimestamp(log.get("timestamp", 0)).strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{ts}] {log.get('admin_username')} | {log.get('action')} | {log.get('resource_type')} | {log.get('resource_id', '')} | {log.get('ip_address')}")
    finally:
        await client.close()


async def _export_login_attempts(output_file: str | None = None, limit: int = 1000):
    client, db = await _get_db()
    try:
        cursor = db["admin_login_attempts"].find({}).sort("timestamp", -1).limit(limit)
        attempts = await cursor.to_list(length=limit)

        if output_file:
            with open(output_file, "w", newline="", encoding="utf-8") as f:
                if output_file.endswith(".csv"):
                    writer = csv.DictWriter(f, fieldnames=["username", "ip_address", "success", "timestamp", "failure_reason", "user_agent"])
                    writer.writeheader()
                    for a in attempts:
                        writer.writerow({
                            "username": a.get("username", ""),
                            "ip_address": a.get("ip_address", ""),
                            "success": a.get("success", False),
                            "timestamp": datetime.fromtimestamp(a.get("timestamp", 0)).isoformat(),
                            "failure_reason": a.get("failure_reason", ""),
                            "user_agent": a.get("user_agent", ""),
                        })
                else:
                    json.dump(attempts, f, indent=2, default=str)
            print(f"✓ Exported {len(attempts)} login attempt entries to '{output_file}'.")
        else:
            for a in attempts:
                ts = datetime.fromtimestamp(a.get("timestamp", 0)).strftime("%Y-%m-%d %H:%M:%S")
                status = "✓" if a.get("success") else "✗"
                print(f"[{ts}] {status} {a.get('username')} from {a.get('ip_address')} | {a.get('failure_reason', '')}")
    finally:
        await client.close()


async def _list_admins():
    client, db = await _get_db()
    try:
        cursor = db["admin_users"].find({}, {"password_hash": 0}).sort("created_at_timestamp", 1)
        admins = await cursor.to_list(length=100)
        if not admins:
            print("No admin accounts found.")
            return
        print(f"{'Username':<20} {'Display Name':<25} {'Role':<15} {'Active':<8} {'Last Login'}")
        print("-" * 90)
        for a in admins:
            last_login = ""
            if a.get("last_login_timestamp"):
                last_login = datetime.fromtimestamp(a["last_login_timestamp"]).strftime("%Y-%m-%d %H:%M")
            active = "✓" if a.get("is_active") else "✗"
            print(f"{a.get('username', ''):<20} {a.get('display_name', ''):<25} {a.get('role', ''):<15} {active:<8} {last_login}")
    finally:
        await client.close()


def _usage():
    print(__doc__)
    sys.exit(0)


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        _usage()

    command = args[0]

    if command == "create-admin":
        asyncio.run(_create_admin())

    elif command == "rotate-password":
        if len(args) < 2:
            print("Usage: python cli.py rotate-password <username>")
            sys.exit(1)
        asyncio.run(_rotate_password(args[1]))

    elif command == "deactivate-admin":
        if len(args) < 2:
            print("Usage: python cli.py deactivate-admin <username>")
            sys.exit(1)
        asyncio.run(_deactivate_admin(args[1]))

    elif command == "activate-admin":
        if len(args) < 2:
            print("Usage: python cli.py activate-admin <username>")
            sys.exit(1)
        asyncio.run(_activate_admin(args[1]))

    elif command == "clear-user-locks":
        asyncio.run(_clear_user_locks())

    elif command == "clear-user-lock":
        if len(args) < 2:
            print("Usage: python cli.py clear-user-lock <user_id>")
            sys.exit(1)
        asyncio.run(_clear_user_locks(args[1]))

    elif command == "export-audit-log":
        output = None
        limit = 1000
        i = 1
        while i < len(args):
            if args[i] == "--output" and i + 1 < len(args):
                output = args[i + 1]
                i += 2
            elif args[i] == "--limit" and i + 1 < len(args):
                limit = int(args[i + 1])
                i += 2
            else:
                i += 1
        asyncio.run(_export_audit_log(output, limit))

    elif command == "export-login-attempts":
        output = None
        limit = 1000
        i = 1
        while i < len(args):
            if args[i] == "--output" and i + 1 < len(args):
                output = args[i + 1]
                i += 2
            elif args[i] == "--limit" and i + 1 < len(args):
                limit = int(args[i + 1])
                i += 2
            else:
                i += 1
        asyncio.run(_export_login_attempts(output, limit))

    elif command == "list-admins":
        asyncio.run(_list_admins())

    else:
        print(f"Unknown command: {command!r}")
        _usage()


if __name__ == "__main__":
    main()
