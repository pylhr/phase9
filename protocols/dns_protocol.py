"""
Protocol Layer — DNS resolution.

This module talks directly to DNS resolvers using dnspython. It has no
knowledge of Qt, threads, or the UI — it just performs real lookups and
returns plain data-layer objects. The service layer is responsible for
running this off the UI thread.
"""
from __future__ import annotations

import time
from typing import Optional

import dns.resolver
import dns.exception

from data.models import DNSRecord, DNSResult

# Record types we attempt for every domain. Some domains won't have all of
# these (e.g. most domains have no MX record) — that's a normal, expected
# per-type failure, not a fatal error for the whole lookup.
RECORD_TYPES = ["A", "AAAA", "CNAME", "MX", "NS", "TXT"]


def resolve_domain(domain: str, nameserver: Optional[str] = None, timeout: float = 5.0) -> DNSResult:
    """
    Perform a real DNS lookup for `domain` across all RECORD_TYPES.

    Args:
        domain: hostname to resolve, e.g. "github.com" (scheme/path stripped by caller)
        nameserver: optional specific resolver IP to query, e.g. "8.8.8.8".
                    If None, the system's configured resolver is used.
        timeout: per-query timeout in seconds.

    Returns:
        DNSResult with whatever records were found and any per-type errors.
    """
    resolver = dns.resolver.Resolver()
    resolver.timeout = timeout
    resolver.lifetime = timeout

    if nameserver:
        resolver.nameservers = [nameserver]
        resolver_label = nameserver
    else:
        # Report the resolver(s) actually in use for transparency in the UI.
        resolver_label = ", ".join(resolver.nameservers) if resolver.nameservers else "system default"

    records: list[DNSRecord] = []
    errors: dict[str, str] = {}

    start = time.perf_counter()

    for rtype in RECORD_TYPES:
        try:
            answer = resolver.resolve(domain, rtype)
            ttl = answer.rrset.ttl if answer.rrset is not None else None

            for rdata in answer:
                if rtype == "MX":
                    records.append(DNSRecord(
                        record_type=rtype,
                        value=str(rdata.exchange).rstrip("."),
                        ttl=ttl,
                        priority=rdata.preference,
                    ))
                else:
                    records.append(DNSRecord(
                        record_type=rtype,
                        value=str(rdata).rstrip("."),
                        ttl=ttl,
                    ))

        except dns.resolver.NoAnswer:
            # Domain exists but has no records of this type — normal, not an error.
            continue
        except dns.resolver.NXDOMAIN:
            errors[rtype] = "Domain does not exist (NXDOMAIN)"
            # No point trying other record types for a domain that doesn't exist.
            break
        except dns.exception.Timeout:
            errors[rtype] = f"Query timed out after {timeout}s"
        except Exception as exc:  # noqa: BLE001 - surface any resolver error to the UI
            errors[rtype] = str(exc)

    elapsed_ms = (time.perf_counter() - start) * 1000

    return DNSResult(
        domain=domain,
        resolver_used=resolver_label,
        query_time_ms=elapsed_ms,
        records=records,
        errors=errors,
    )
