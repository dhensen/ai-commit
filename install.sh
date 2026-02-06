python3 -m venv venv
venv/bin/pip install -r requirements.txt

rm ~/bin/commit

# this write a python file that uses python in the venv, then invoke commit.py
# call this file commit and install it in ~/bin
cat <<EOF > ~/bin/commit
#!/usr/bin/env zsh
$PWD/venv/bin/python3 $PWD/commit.py "\$@"
EOF

chmod +x ~/bin/commit
