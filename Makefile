.PHONY: lint

lint:
	pylint $$(git ls-files '*.py')	
	