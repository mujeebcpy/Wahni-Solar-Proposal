"""Keep historical proposals and remove obsolete package configuration columns."""


def execute():
    from wahni_solar.wahni_solar_proposal.upgrade import finish_legacy_configuration

    finish_legacy_configuration()
