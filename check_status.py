import sys, json

print(sys.argv[1])
result = json.loads(sys.argv[1])

errors = result['error']

for error in errors.keys():
    e = errors[error]
    if 'system' in errors[error]:
        print(e)
        exit(1)
