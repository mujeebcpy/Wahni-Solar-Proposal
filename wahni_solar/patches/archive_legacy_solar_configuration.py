"""Archive retired solar configuration before the package schema changes."""


def execute():
    from wahni_solar.wahni_solar_proposal.upgrade import prepare_legacy_configuration

    prepare_legacy_configuration()
