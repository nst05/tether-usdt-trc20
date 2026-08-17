#!/usr/bin/env python3
import sys, re
from collections import defaultdict, deque
from msp430dis import Mem, disasm_one, render, REG
REGNAMES=set(REG)

img = open('fw.bin','rb').read()
mem = Mem(img, 0)

CODE_LO, CODE_HI = 0x1100, 0xFFDF

VECNAMES = ['DAC12_DMA','PORT2','USART1_TX','USART1_RX','PORT1','TIMERA1','TIMERA0','ADC12',
            'USART0_TX','USART0_RX','WDT','COMPARATOR_A','TIMERB1','TIMERB0','NMI','RESET']

# ---- MSP430F1xx/F16x peripheral map ----
PERIPH = {
0x0000:'IE1',0x0001:'IE2',0x0002:'IFG1',0x0003:'IFG2',0x0004:'ME1',0x0005:'ME2',
0x0018:'P3IN',0x0019:'P3OUT',0x001A:'P3DIR',0x001B:'P3SEL',
0x001C:'P4IN',0x001D:'P4OUT',0x001E:'P4DIR',0x001F:'P4SEL',
0x0020:'P1IN',0x0021:'P1OUT',0x0022:'P1DIR',0x0023:'P1IFG',0x0024:'P1IES',0x0025:'P1IE',0x0026:'P1SEL',
0x0028:'P2IN',0x0029:'P2OUT',0x002A:'P2DIR',0x002B:'P2IFG',0x002C:'P2IES',0x002D:'P2IE',0x002E:'P2SEL',
0x0030:'P5IN',0x0031:'P5OUT',0x0032:'P5DIR',0x0033:'P5SEL',
0x0034:'P6IN',0x0035:'P6OUT',0x0036:'P6DIR',0x0037:'P6SEL',
0x0056:'DCOCTL',0x0057:'BCSCTL1',0x0058:'BCSCTL2',
0x0059:'CACTL1',0x005A:'CACTL2',0x005B:'CAPD',
0x0070:'U0CTL',0x0071:'U0TCTL',0x0072:'U0RCTL',0x0073:'U0MCTL',0x0074:'U0BR0',0x0075:'U0BR1',0x0076:'U0RXBUF',0x0077:'U0TXBUF',
0x0078:'U1CTL',0x0079:'U1TCTL',0x007A:'U1RCTL',0x007B:'U1MCTL',0x007C:'U1BR0',0x007D:'U1BR1',0x007E:'U1RXBUF',0x007F:'U1TXBUF',
0x0120:'WDTCTL',0x0128:'FCTL1',0x012A:'FCTL2',0x012C:'FCTL3',
0x0130:'MPY',0x0132:'MPYS',0x0134:'MAC',0x0136:'MACS',0x0138:'OP2',0x013A:'RESLO',0x013C:'RESHI',0x013E:'SUMEXT',
0x0160:'TACTL',0x0162:'TACCTL0',0x0164:'TACCTL1',0x0166:'TACCTL2',0x012E:'TAIV',
0x0170:'TAR',0x0172:'TACCR0',0x0174:'TACCR1',0x0176:'TACCR2',
0x0180:'TBCTL',0x0182:'TBCCTL0',0x0184:'TBCCTL1',0x0186:'TBCCTL2',0x0188:'TBCCTL3',
0x018A:'TBCCTL4',0x018C:'TBCCTL5',0x018E:'TBCCTL6',0x011E:'TBIV',
0x0190:'TBR',0x0192:'TBCCR0',0x0194:'TBCCR1',0x0196:'TBCCR2',0x0198:'TBCCR3',
0x019A:'TBCCR4',0x019C:'TBCCR5',0x019E:'TBCCR6',
0x01A0:'ADC12CTL0',0x01A2:'ADC12CTL1',0x01A4:'ADC12IFG',0x01A6:'ADC12IE',0x01A8:'ADC12IV',
}
for i in range(16):
    PERIPH[0x0080+i]='ADC12MCTL%d'%i
    PERIPH[0x0140+i*2]='ADC12MEM%d'%i

def annot(txt):
    def sub(m):
        a=int(m.group(1),16)
        n=PERIPH.get(a)
        return '&'+n if n else m.group(0)
    return re.sub(r'&0x([0-9a-f]{4})', sub, txt)

# ---- recursive traversal ----
insns = {}
funcs = set()
callers = defaultdict(set)
xrefs = defaultdict(set)
entries = []
for i in range(16):
    a=0xFFE0+i*2
    v=img[a]|(img[a+1]<<8)
    entries.append((v, VECNAMES[i]))

vecmap = {v:n for v,n in entries}
queue = deque()
seen=set()
for v,n in entries:
    if CODE_LO<=v<=CODE_HI:
        queue.append(v); funcs.add(v)

# Точки входа, достижимые только через косвенные/таймерные диспетчеры
# (add &TAIV,pc; периодический опрос кнопок; вызовы через указатель).
SEEDS = [0x2F80, 0x2F1E, 0x3384, 0x4466, 0x4D76, 0x50B4, 0x537E,
         0x602E, 0x5FBE, 0x604C, 0x60F4, 0x6114, 0x7EE0]
for v in SEEDS:
    if CODE_LO<=v<=CODE_HI:
        queue.append(v); funcs.add(v)

# also seed from any word in flash that points to a plausible function start?
# do main pass first
jumptables={}

def expand_jumptable(tbl_addr):
    """Entries are 4-byte `br #imm` (30 40 lo hi). Collect while they look valid."""
    tgts=[]
    a=tbl_addr
    while a+3 <= CODE_HI:
        if img[a]!=0x30 or img[a+1]!=0x40: break
        t=img[a+2]|(img[a+3]<<8)
        if not (CODE_LO<=t<=CODE_HI): break
        tgts.append((a,t))
        a+=4
        if len(tgts)>64: break
    return tgts

while queue:
    a=queue.popleft()
    while True:
        if a in seen or not (CODE_LO<=a<=CODE_HI): break
        ins = disasm_one(mem, a)
        if ins is None: break
        seen.add(a)
        insns[a]=ins
        if ins.mn=='add' and ins.dst=='pc' and ins.src in REGNAMES:
            tbl=a+ins.size
            ents=expand_jumptable(tbl)
            if ents:
                jumptables[tbl]=[t for _,t in ents]
                for ea,t in ents:
                    funcs.add(t); callers[t].add(a)
                    if t not in seen: queue.append(t)
                    # mark the br slot itself as decoded
                    bi=disasm_one(mem, ea)
                    if bi: insns[ea]=bi; seen.add(ea)
            break
        if ins.mn=='.word': break
        if ins.is_call and ins.target and CODE_LO<=ins.target<=CODE_HI:
            funcs.add(ins.target); callers[ins.target].add(a)
            if ins.target not in seen: queue.append(ins.target)
        if ins.target is not None and not ins.is_call and CODE_LO<=ins.target<=CODE_HI:
            if ins.mn.startswith('j') or ins.mn=='br':
                xrefs[ins.target].add(a)
                if ins.target not in seen: queue.append(ins.target)
        if ins.stops or ins.is_ret:
            break
        a += ins.size

print('# reached instructions: %d, bytes covered: %d'%(len(insns), sum(i.size for i in insns.values())))
print('# functions found: %d'%len(funcs))

# ---- emit listing ----
out=open('dis.txt','w')
out.write('; MSP430 firmware, recursive-descent disassembly\n')
out.write('; vectors:\n')
for i in range(16):
    a=0xFFE0+i*2; v=img[a]|(img[a+1]<<8)
    out.write(';   0x%04X %-14s -> 0x%04X\n'%(a, VECNAMES[i], v))
out.write('\n')

addrs=sorted(insns)
prev_end=None
for a in addrs:
    ins=insns[a]
    if prev_end is not None and a!=prev_end:
        out.write('\n; ---- gap 0x%04X-0x%04X (%d bytes data/unreached) ----\n\n'%(prev_end,a-1,a-prev_end))
    if a in funcs:
        lbl = vecmap.get(a)
        out.write('\n%s:\n'%('%s_ISR (0x%04X)'%(lbl,a) if lbl else 'sub_%04X'%a))
        if callers[a]:
            out.write(';  callers: %s\n'%', '.join('0x%04X'%c for c in sorted(callers[a])))
    elif a in xrefs:
        out.write('loc_%04X:\n'%a)
    hexb=' '.join('%02x %02x'%(w&0xFF,w>>8) for w in ins.words)
    out.write('    %04x:  %-24s %s\n'%(a, hexb, annot(render(ins))))
    prev_end=a+ins.size
out.close()
print('# wrote dis.txt')

# ---- RAM variable census ----
ramrefs=defaultdict(int)
for a,ins in insns.items():
    for t in (ins.src, ins.dst):
        if t and t.startswith('&0x'):
            v=int(t[3:],16)
            if 0x0200<=v<0x0A00: ramrefs[v]+=1
print('# distinct RAM globals referenced: %d'%len(ramrefs))
import json
json.dump({'jumptables':{('0x%04X'%k):['0x%04X'%t for t in v] for k,v in jumptables.items()},'funcs':sorted(funcs),'ram':{('0x%04X'%k):v for k,v in sorted(ramrefs.items())},
           'callers':{('0x%04X'%k):sorted('0x%04X'%c for c in v) for k,v in callers.items()}},
          open('meta.json','w'), indent=1)
