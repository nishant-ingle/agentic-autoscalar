.PHONY: default help

default: help

%:
	@$(MAKE) -C project $@

help:
	@$(MAKE) -C project help
