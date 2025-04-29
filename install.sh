python3 -m venv venv
venv/bin/pip install -r requirements.txt

# this write a python file that uses python in the venv, then invoke commit.py
# call this file commit and install it in ~/bin
mkdir -p ~/.local/bin

cat <<EOF > ~/.local/bin/commit
#!/bin/bash
source $PWD/venv/bin/activate
python $PWD/commit.py
EOF

chmod +x ~/.local/bin/commit
