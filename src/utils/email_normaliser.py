from __future__ import annotations

import asyncio
import dataclasses
import enum
import logging
from email import utils

import aiodns
from aiodns import error
from pycares import DNSResult, MXRecordData


class Rules(enum.Flag):
    """Represents what features a mailbox provider supports in dynamic
    aliasing of email addresses.

    Used to determine how to normalize provider specific email addresses.
    """

    DASH_ADDRESSING = enum.auto()
    PLUS_ADDRESSING = enum.auto()
    LOCAL_PART_AS_HOSTNAME = enum.auto()
    STRIP_PERIODS = enum.auto()


class MailboxProvider:
    """Base class to define the contract for the mail providers"""

    Flags: Rules
    MXDomains: set[str]

    __name__: str


class Apple(MailboxProvider):
    Flags: Rules = Rules.PLUS_ADDRESSING
    MXDomains: set[str] = {"icloud.com"}


class Fastmail(MailboxProvider):
    Flags: Rules = Rules.PLUS_ADDRESSING ^ Rules.LOCAL_PART_AS_HOSTNAME
    MXDomains: set[str] = {"messagingengine.com"}


class Google(MailboxProvider):
    Flags: Rules = Rules.PLUS_ADDRESSING ^ Rules.STRIP_PERIODS
    MXDomains: set[str] = {"google.com", "googlemail.com"}


class Microsoft(MailboxProvider):
    Flags: Rules = Rules.PLUS_ADDRESSING
    MXDomains: set[str] = {"outlook.com", "hotmail.com"}


class ProtonMail(MailboxProvider):
    Flags: Rules = Rules.PLUS_ADDRESSING
    MXDomains: set[str] = {"protonmail.ch"}


class Rackspace(MailboxProvider):
    Flags: Rules = Rules.PLUS_ADDRESSING
    MXDomains: set[str] = {"emailsrvr.com"}


class Yahoo(MailboxProvider):
    Flags: Rules = Rules.DASH_ADDRESSING
    MXDomains: set[str] = {"yahoodns.net"}


class Yandex(MailboxProvider):
    Flags: Rules = Rules.PLUS_ADDRESSING
    MXDomains: set[str] = {"mx.yandex.net", "yandex.ru"}


class Zoho(MailboxProvider):
    Flags: Rules = Rules.PLUS_ADDRESSING
    MXDomains: set[str] = {"zoho.com"}


Providers: list[type[MailboxProvider]] = [Apple, Fastmail, Google, Microsoft, ProtonMail, Rackspace, Yahoo, Yandex, Zoho]

LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class Result:
    """Instances of the :class:`~email_normalize.Result` class contain data
    from the email normalization process.

    :param address: The address that was normalized
    :type address: str
    :param normalized_address: The normalized version of the address
    :type normalized_address: str
    :param mx_records: A list of tuples representing the priority and host of
        the MX records found for the email address. If empty, indicates a
        failure to lookup the domain part of the email address.
    :type mx_records: :data:`~email_normalize.MXRecords`
    :param mailbox_provider: String that represents the mailbox provider name
        - is `None` if the mailbox provider could not be detected or
        was unsupported.
    :type mailbox_provider: str

    .. note:: If during the normalization process the MX records could not be
        resolved, the ``mx_records`` attribute will be an empty :class:`list`
        and the ``mailbox_provider`` attribute will be :data:`None`.

    **Example**

    .. code-block:: python

        @dataclasses.dataclass(frozen=True)
        class Result:
            address = 'Gavin.M.Roy+ignore-spam@gmail.com'
            normalized_address = 'gavinmroy@gmail.com'
            mx_records =     [
                (5, 'gmail-smtp-in.l.google.com'),
                (10, 'alt1.gmail-smtp-in.l.google.com'),
                (20, 'alt2.gmail-smtp-in.l.google.com'),
                (30, 'alt3.gmail-smtp-in.l.google.com'),
                (40, 'alt4.gmail-smtp-in.l.google.com')
            ]
            mailbox_provider = 'Gmail'

    """

    address: str
    cleaned_email: str
    mailbox_provider: str | None = None


class Normalizer:
    """Class for normalizing an email address and resolving MX records.

    Normalization is processed by splitting the local and domain parts of the
    email address and then performing DNS resolution for the MX records
    associated with the domain part of the address. The MX records are
    processed against a set of mailbox provider specific rules. If a match
    is found for the MX record hosts, the rules are applied to the email
    address.

    This class implements a least frequent recently used cache that respects
    the DNS TTL returned when performing MX lookups. Data is cached at the
    **module** level.

    **Usage Example**

    .. code-block:: python

        async def normalize(email_address: str) -> email_normalize.Result:
            normalizer = email_normalize.Normalizer()
            return await normalizer.normalize('foo@bar.io')

    :param name_servers: Optional list of hostnames to use for DNS resolution
    :type name_servers: list(str) or None
    :param int cache_limit: The maximum number of domain results that are
        cached. Defaults to `1024`.

    :param bool cache_failures: Toggle the behavior of caching DNS resolution
        failures for a given domain. When enabled, failures will be cached
        for `failure_ttl` seconds. Defaults to `True`.
    :param int failure_ttl: Duration in seconds to cache DNS failures. Only
        works when `cache_failures` is set to `True`. Defaults to `300`
        seconds.

    """

    def __init__(
        self,
        name_servers: list[str] | None = None,
        cache_failures: bool = True,
        failure_ttl: int = 300,
    ):
        self._resolver = aiodns.DNSResolver(name_servers)
        self.cache_failures = cache_failures
        self.failure_ttl = failure_ttl

        self._cache: dict[str, list[str]] = {}

    @staticmethod
    def dnsresult_to_mx_results(result: DNSResult) -> list[str]:
        mx_results: list[str] = []

        for record in [*result.answer, *result.authority, *result.additional]:
            data = record.data

            if isinstance(data, MXRecordData):
                mx_results.append(data.exchange)

        return mx_results

    async def mx_records(self, domain_part: str) -> list[str]:
        """Resolve MX records for a domain returning a list of tuples with the
        MX priority and value.

        :param domain_part: The domain to resolve MX records for
        :type domain_part: str
        :rtype:  :data:`~email_normalize.MXRecords`

        """

        try:
            return self._cache[domain_part]
        except KeyError:
            pass

        try:
            dns_result = await self._resolver.query_dns(domain_part, "MX")
            mx_hosts = self.dnsresult_to_mx_results(dns_result)

        except error.DNSError as err:
            LOGGER.debug("Failed to resolve %r: %s", domain_part, err)
            if not self.cache_failures:
                return []
            mx_hosts = []
        else:
            mx_hosts = mx_hosts

        self._cache[domain_part] = mx_hosts
        return mx_hosts

    async def normalize(self, email_address: str) -> Result:
        """Return a :class:`~email_normalize.Result` instance containing the
        original address, the normalized address, the MX records found, and
        the detected mailbox provider.

        .. note:: If the MX records could not be resolved, the ``mx_records``
            attribute of the result will be an empty :class:`list` and the
            ``mailbox_provider`` will be :data:`None`.

        :param email_address: The address to normalize
        :rtype: :class:`~email_normalize.Result`

        """
        address = utils.parseaddr(email_address)
        local_part, domain_part = address[1].lower().split("@")
        mx_records = await self.mx_records(domain_part)
        provider = self._lookup_provider(mx_records)
        if provider:
            if provider.Flags & Rules.LOCAL_PART_AS_HOSTNAME:
                local_part, domain_part = self._local_part_as_hostname(local_part, domain_part)
            if provider.Flags & Rules.STRIP_PERIODS:
                local_part = local_part.replace(".", "")
            if provider.Flags & Rules.PLUS_ADDRESSING:
                local_part = local_part.split("+")[0]
            if provider.Flags & Rules.DASH_ADDRESSING:
                local_part = local_part.split("-")[0]
        return Result(email_address, "@".join([local_part, domain_part]), provider.__name__ if provider else None)

    @staticmethod
    def _local_part_as_hostname(local_part: str, domain_part: str) -> tuple[str, str]:
        domain_segments = domain_part.split(".")
        if len(domain_segments) > 2:
            local_part = domain_segments[0]
            domain_part = ".".join(domain_segments[1:])
        return local_part, domain_part

    @staticmethod
    def _lookup_provider(mx_records: list[str]) -> type[MailboxProvider] | None:
        for host in mx_records:
            lchost = host.lower()
            for provider in Providers:
                for domain in provider.MXDomains:
                    if lchost.endswith(domain):
                        return provider


async def normalize(email_address: str) -> Result:
    """Normalize an email address

    This method abstracts the :mod:`asyncio` base for this library and
    provides a blocking function. If you intend to use this library as part of
    an :mod:`asyncio` based application, it is recommended that you use
    the :meth:`~email_normalize.Normalizer.normalize` instead.

    .. note:: If the MX records could not be resolved, the ``mx_records``
        attribute of the result will be an empty :class:`list` and the
        ``mailbox_provider`` attribute will be :data:`None`.

    **Usage Example**

    .. code-block:: python

        import email_normalize

        result = email_normalize.normalize('foo@bar.io')

    :param email_address: The address to normalize
    """
    normalizer = Normalizer()
    return await normalizer.normalize(email_address)
