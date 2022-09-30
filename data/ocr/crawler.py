import re
file = 'data\ocr\shipname_source.html'
re_rk_wsrwiki = r'</tr><tr><td width="162"><center><b>.{0,60}</b></center></td>'
re_name_wsrwiki = r'</tr><tr><td width="162" height="56"><center><b><a href="https://www.zjsnrwiki.com/wiki/.{0,100} title=.{0,60}</a></b></center></td>'
def extract(str):
    res = ""
    rks = re.findall(re_rk_wsrwiki,str)
    names = re.findall(re_name_wsrwiki,str)
    print(len(rks), len(names))
    """for rk in rks:
        rk = rk[40:rk.find("</b>")]
        print(rk)"""
    
    for rk, name in zip(rks, names):
        rk = rk[40:rk.find("</b>")]
        _title_idx = name.find("title") + 7
        name = name[_title_idx:]
        name = name[:name.index("\"")]
        res += f"No.{rk}: # {name}\n"
        res += f"  - {name}\n"
    return res
with open(r"data\ocr\shipname_source.html", mode="r", encoding='utf-8') as f:
    # print(f.read())
    ori = extract(f.read())
with open("data/ocr/_shipname_example.yaml", mode="w+", encoding='utf-8') as f:
    f.write(ori)