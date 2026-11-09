.PHONY: install seed test clean-db

install:
	pip install -r requirements.txt

seed:
	PYTHONPATH=. python -m epic5.approach_syn_generator epic5/config.yaml

test:
	pytest tests/epic5/test_approach_syn_generator.py -v

clean-db:
	psql -U agentic_autoscalar -d agentic_autoscalar_db -c "TRUNCATE TABLE rag_documents RESTART IDENTITY;"
