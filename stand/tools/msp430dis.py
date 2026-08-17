#!/usr/bin/env python3
"""Recursive-descent MSP430 disassembler for firmware analysis."""
import sys, struct
from collections import defaultdict

REG = ['pc','sp','sr','cg','r4','r5','r6','r7','r8','r9','r10','r11','r12','r13','r14','r15']

DOUBLE = {4:'mov',5:'add',6:'addc',7:'subc',8:'sub',9:'cmp',0xA:'dadd',0xB:'bit',0xC:'bic',0xD:'bis',0xE:'xor',0xF:'and'}
SINGLE = {0:'rrc',1:'swpb',2:'rra',3:'sxt',4:'push',5:'call',6:'reti'}
JMP    = {0:'jnz',1:'jz',2:'jnc',3:'jc',4:'jn',5:'jge',6:'jl',7:'jmp'}

class Insn:
    __slots__=('addr','size','mn','bw','src','dst','target','words','is_call','is_ret','stops','raw')
    def __init__(self):
        self.target=None; self.is_call=False; self.is_ret=False; self.stops=False; self.words=[]

class Mem:
    def __init__(self, img, base=0):
        self.img=img; self.base=base
    def w(self,a):
        o=a-self.base
        if o<0 or o+1>=len(self.img): return None
        return self.img[o]|(self.img[o+1]<<8)
    def b(self,a):
        o=a-self.base
        if o<0 or o>=len(self.img): return None
        return self.img[o]

def const_gen(reg, as_):
    """Return immediate value for constant generator, or None."""
    if reg==2:
        return {2:4, 3:8}.get(as_)
    if reg==3:
        return {0:0, 1:1, 2:2, 3:-1}[as_]
    return None

def fmt_num(v):
    if v is None: return '?'
    if -9 <= v <= 9: return str(v)
    return ('-0x%x'%-v) if v<0 else '0x%x'%v

def decode_operand(mem, reg, mode, is_src, pc_after, fetch):
    """Returns (text, extra_words_used, absolute_target_or_None, immediate_or_None)"""
    cg = const_gen(reg, mode) if is_src else (const_gen(reg,mode) if reg in (2,3) and mode in (2,3) else None)
    if is_src and reg in (2,3):
        v = const_gen(reg, mode)
        if v is not None:
            return ('#'+fmt_num(v), 0, None, v)
    if mode==0:
        return (REG[reg], 0, None, None)
    if mode==1:
        x = fetch()
        if reg==0:   # symbolic PC-relative
            t=(pc_after + x) & 0xFFFF
            return ('0x%04x'%t, 1, t, None)
        if reg==2:   # absolute
            return ('&0x%04x'%x, 1, x, None)
        sx = x-0x10000 if x>=0x8000 else x
        return ('%s(%s)'%(fmt_num(sx), REG[reg]), 1, None, None)
    if mode==2:
        return ('@'+REG[reg], 0, None, None)
    if mode==3:
        if reg==0:   # immediate
            x = fetch()
            sx = x-0x10000 if x>=0x8000 else x
            return ('#'+fmt_num(sx if abs(sx)<0x8000 else x), 1, None, x)
        return ('@%s+'%REG[reg], 0, None, None)
    return ('?',0,None,None)

def disasm_one(mem, addr):
    w = mem.w(addr)
    if w is None: return None
    ins = Insn(); ins.addr=addr; ins.bw=False; ins.src=None; ins.dst=None
    cur = [addr+2]
    words=[w]
    def fetch():
        x = mem.w(cur[0])
        if x is None: x=0
        words.append(x)
        cur[0]+=2
        return x

    op = (w>>12)&0xF
    if op==1:
        sub=(w>>7)&0x1F
        # 000100 ooo b Ad dst
        o3=(w>>7)&0x7
        if (w>>10)&0x3 != 0:
            ins.mn='.word'; ins.src='0x%04x'%w; ins.size=2; ins.words=words; ins.stops=True; return ins
        mn = SINGLE.get(o3)
        if mn is None:
            ins.mn='.word'; ins.src='0x%04x'%w; ins.size=2; ins.words=words; ins.stops=True; return ins
        bw=(w>>6)&1
        ad=(w>>4)&3
        reg=w&0xF
        if mn=='reti':
            ins.mn='reti'; ins.size=2; ins.is_ret=True; ins.stops=True; ins.words=words; return ins
        txt,_,tgt,imm = decode_operand(mem, reg, ad, True, cur[0]+0, fetch)
        # PC-relative needs pc after the extension word
        if ad==1 and reg==0:
            base = addr+4
            x = words[1]
            t=(base+x)&0xFFFF
            txt='0x%04x'%t; tgt=t
        ins.mn=mn+('.b' if bw else ''); ins.bw=bool(bw); ins.dst=txt; ins.size=cur[0]-addr
        ins.words=words
        if mn=='call':
            ins.is_call=True
            ins.target = imm if (reg==0 and ad==3) else tgt
            if reg==0 and ad==3: ins.target=words[1]
        elif mn=='push':
            pass
        # mov to PC style handled in double
        return ins
    elif op==2 or op==3:
        cond=(w>>10)&7
        off=w&0x3FF
        if off>=0x200: off-=0x400
        t=(addr+2+off*2)&0xFFFF
        ins.mn=JMP[cond]; ins.dst='0x%04x'%t; ins.target=t; ins.size=2; ins.words=words
        if cond==7: ins.stops=True
        return ins
    elif op>=4:
        mn=DOUBLE[op]
        sreg=(w>>8)&0xF; ad=(w>>7)&1; bw=(w>>6)&1; as_=(w>>4)&3; dreg=w&0xF
        stxt,_,stgt,simm = decode_operand(mem, sreg, as_, True, 0, fetch)
        if as_==1 and sreg==0:
            t=(addr+2+words[1])&0xFFFF; stxt='0x%04x'%t; stgt=t
        n_after_src=len(words)
        dtxt,_,dtgt,_ = decode_operand(mem, dreg, ad, False, 0, fetch)
        if ad==1 and dreg==0:
            xi = n_after_src
            t=(addr+2*xi+words[xi])&0xFFFF; dtxt='0x%04x'%t; dtgt=t
        ins.mn=mn+('.b' if bw else ''); ins.bw=bool(bw)
        ins.src=stxt; ins.dst=dtxt; ins.size=cur[0]-addr; ins.words=words
        # ret = mov @sp+, pc
        if mn=='mov' and dreg==0 and ad==0:
            if sreg==1 and as_==3:
                ins.mn='ret'; ins.src=None; ins.dst=None; ins.is_ret=True; ins.stops=True
            else:
                ins.stops=True
                if sreg==0 and as_==3: ins.target=words[1]
                elif stgt is not None and as_==1: ins.target=None
        if mn in ('add','sub') and dreg==0 and ad==0:
            ins.stops=True
        return ins
    ins.mn='.word'; ins.src='0x%04x'%w; ins.size=2; ins.words=words; ins.stops=True
    return ins

# ---- emulated instruction rendering ----
def render(ins):
    mn=ins.mn; s=ins.src; d=ins.dst
    base=mn.split('.')[0]; suf='.b' if ins.bw else ''
    e=None
    if base=='mov':
        if s=='#0': e=('clr'+suf, d)
        elif d=='pc': e=('br', s)
    elif base=='add':
        if s=='#1': e=('inc'+suf, d)
        elif s=='#2': e=('incd'+suf, d)
        elif s==d: e=('rla'+suf, d)
    elif base=='addc':
        if s=='#0': e=('adc'+suf, d)
        elif s==d: e=('rlc'+suf, d)
    elif base=='subc':
        if s=='#0': e=('sbc'+suf, d)
    elif base=='sub':
        if s=='#1': e=('dec'+suf, d)
        elif s=='#2': e=('decd'+suf, d)
    elif base=='cmp':
        if s=='#0': e=('tst'+suf, d)
    elif base=='dadd':
        if s=='#0': e=('dadc'+suf, d)
    elif base=='bic':
        if d=='sr':
            if s=='#1': e=('clrc',None)
            elif s=='#2': e=('clrz',None)
            elif s=='#4': e=('clrn',None)
            elif s=='#8': e=('dint',None)
    elif base=='bis':
        if d=='sr':
            if s=='#1': e=('setc',None)
            elif s=='#2': e=('setz',None)
            elif s=='#4': e=('setn',None)
            elif s=='#8': e=('eint',None)
    elif base=='xor':
        if s=='#-1': e=('inv'+suf, d)
    if e:
        m,o=e
        return m if o is None else '%-7s %s'%(m,o)
    if s is None and d is None: return mn
    if s is None: return '%-7s %s'%(mn,d)
    return '%-7s %s, %s'%(mn,s,d)
