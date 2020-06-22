VENV = $(PWD)/.venv3
BIN = $(VENV)/bin

install: $(VENV)

$(VENV): requirements.txt
	[ -d $@ ] || python3 -m venv $@
	$(BIN)/pip3 install -r $<
	touch $@
