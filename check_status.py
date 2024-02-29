import sys, json

print(sys.argv[1])
result = json.loads(sys.argv[1])

errors = result["error"]

for error in errors.keys():
    e = errors[error]
    if e:
        if "system" in e:
            print(e)
            exit(1)
