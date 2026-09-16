" Run Python linting and type checking through the uv project environment.
let g:ale_linters = {'python': ['flake8', 'pyright']}
let g:ale_python_flake8_auto_uv = 1
let g:ale_python_pyright_auto_uv = 1
let g:ale_lint_on_text_changed = 'always'
let g:ale_lint_on_save = 1
