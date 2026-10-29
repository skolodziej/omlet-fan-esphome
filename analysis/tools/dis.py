# Disassemble an ESP32-S3 app image and annotate l32r literals.
# usage: OBJDUMP=xtensa-esp32s3-elf-objdump python3 dis.py app.bin out.txt
import struct, subprocess, sys, re, os
img=open(sys.argv[1],'rb').read(); out=sys.argv[2]
OBJ=os.environ.get('OBJDUMP','xtensa-esp32s3-elf-objdump')
n=img[1]; p=24; segs=[]
for i in range(n):
    addr,ln=struct.unpack('<II',img[p:p+8]); segs.append((addr,img[p+8:p+8+ln])); p+=8+ln
mem={}
def rd32(a):
    for base,data in segs:
        if base<=a<base+len(data)-3: return struct.unpack('<I',data[a-base:a-base+4])[0]
def cstr(a):
    for base,data in segs:
        if base<=a<base+len(data):
            o=a-base; e=data.find(b'\0',o)
            s=data[o:e]
            if 2<len(s)<200 and all(32<=c<127 or c in(9,10,13,27) for c in s): return s.decode().replace('\n','\\n').replace('\x1b','')
os.makedirs('seg',exist_ok=True)
with open(out,'w') as f:
  for base,data in segs:
    if not (0x40370000<=base<0x403E0000 or 0x42000000<=base<0x44000000): continue
    fn=f'seg/{base:08x}.bin'; open(fn,'wb').write(data)
    r=subprocess.run([OBJ,'-D','-b','binary','-m','xtensa','-EL','--adjust-vma',hex(base),fn],capture_output=True,text=True).stdout
    for line in r.splitlines():
        m=re.search(r'l32r\s+(a\d+), (?:0x)?([0-9a-f]+)',line)
        if m:
            v=rd32(int(m.group(2),16))
            if v is not None:
                s=cstr(v)
                line+=f'   ; ={v:#x}'+(f' "{s}"' if s else '')
        f.write(line+'\n')
