from flask import Flask, make_response, request
from pymarc import Record, Field, parse_xml_to_array
from urllib.parse import urlencode
import pysolr, pymarc, io, json, sys, re, traceback, datetime
import logging
import configparser


#logging.basicConfig(filename='example.log', encoding='utf-8', level=logging.DEBUG)
#logging.basicConfig(filename='example.log', level=logging.DEBUG)
#logging.basicConfig(qualname='primogvi')

GVIURL     = 'http://gvi.bsz-bw.de/solr/GVIPROD'
CONFIGFILE = 'gvi2pnx.ini' 
FLAG       = False

class Config:
    
    def __init__(self, token):
        self._debug       = False
        self._section     = None
        self._token       = None
        self._isil        = None
        self._gviurl      = None
        self._delcategory = "Remote Search Resource"
        self._config = configparser.ConfigParser()
        self._config.read(CONFIGFILE)
        for section in self._config.sections():
            if self._config[section]['TOKEN'] == token:
                self._section = section
                self._token   = token
                try:
                    self._gviurl = self._config[section]['GVIURL']
                except:
                    pass
                try:
                    self._isil = self._config[section]['ISIL']
                except:
                    pass
                try:
                    self._delcategory = self._config[section]['DELCATEGORY']
                except:
                    pass
                try:
                    if self._config[section]['DEBUG'] == "True":
                        self._debug = True 
                        Log('Set Debug Flag to "True"')
                    else:
                        Log('Set Debug Flag to "False"')
                except:
                    Log('Debug Flag ignored')
                    pass
                    
    def get_delcategory(self):
        return self._delcategory
    
    def validate(self, token):
        Log("validating %s" % token)
        if self._token is None:
            return False
        return token == self._token
        
    def get_links(self):
        Log('Config Section: %s' % self._section)
        list = []
        if self._section is not None:
            try:
                for element in self._config[self._section]['LINKS'].split("\n"):
                    Log('Element: %s' % element)
                    link, text = element.split(maxsplit=1)
                    Log('Split:   "%s" "%s"' % (link, text) )
                    if self._debug==True or (self._debug==False and 'debug' not in text.lower()):
                        Log('Append:   "%s" "%s"' % (link, text) )
                        list.append((link,text))
            except:
                pass
        Log('Link Templates: %s' % list)
        return list

    def get_openurls(self):
        Log('Config Section: %s' % self._section)
        list = []
        if self._section is not None:
            try:
                for element in self._config[self._section]['OPENURLS'].split("\n"):
                    Log('Element: %s' % element)
                    link, text = element.split(maxsplit=1)
                    Log('Split:   "%s" "%s"' % (link, text) )
                    list.append((link,text))
            except:
                pass
        Log('OpenURL Templates: %s' % list)
        return list

    def get_baseurls(self):
        Log('Config Section: %s' % self._section)
        list = []
        if self._section is not None:
            try:
                for element in self._config[self._section]['BASEURLS'].split("\n"):
                    Log('Element: %s' % element)
                    link, text = element.split(maxsplit=1)
                    Log('Split:   "%s" "%s"' % (link, text) )
                    list.append((link,text))
            except:
                pass
        Log('OpenURL Templates: %s' % list)
        return list

    def get_isils(self):
        Log('Config Section: %s' % self._section)
        list = []
        if self._section is not None:
            try:
                for element in self._config[self._section]['ISILS'].split("\n"):
                    Log('Element: %s' % element)
                    isil, text = element.split(maxsplit=1)
                    Log('Split:   "%s" "%s"' % (isil, text) )
                    list.append((isil,text))
            except:
                pass
        Log('Isil Templates: %s' % list)
        return list

    def get_filters(self):
        Log('Config Section: %s' % self._section)
        list = []
        if self._section is not None:
            try:
                for element in self._config[self._section]['FILTERS'].split("\n"):
                    Log('Element: %s' % element)
                    list.append(element)
            except:
                pass
        Log('FILTERS Templates: %s' % list)
        return list
        
    def get_isil(self):
        Log('Config Section: %s' % self._section)
        Log('Isil: %s' % self._isil)
        return self._isil
        
    def get_gviurl(self):
        Log('Config Section: %s' % self._section)
        Log('GVIURL: %s' % self._gviurl)
        return self._gviurl


FACETQUERYREPLACE = [
    ('facet_creator','author'),
    ('facet_pfilter','material_content_type'), 
    # ('facet_rtype', 'material_media_type'), 
    ('facet_rtype', 'material_content_type'), 
    ('facet_lang','language'), 
    ('facet_creationdate','publish_date'),
    ('facet_library', 'consortium'),
    ('facet_tlevel',  'material_access'),
    ('facet_topic',    'subject_all')
    ]

MATERIAL_MEDIA_TYPE_MAP = {
  '"books"'    : 'Book',
  '"articles"' : 'Article',
  '"journals"' : 'Journal/Magazine',
  '"images"'   : 'Image',
  '"audio_video"' : 'Video',
}

FACETQUERY_MAP = {
    'facet_creator': 'author_facet',
    'facet_pfilter': 'material_content_type', 
    # 'facet_pfilter': 'material_media_type', 
    'facet_rtype':   'material_content_type', 
    # 'facet_rtype':   'material_media_type', 
    'facet_lang':    'language', 
    'facet_creationdate': 'publish_date',
    'facet_library': 'consortium',
    'facet_tlevel':  'material_access',
    'facet_topic':   'subject_all_facet'
    }

QUERYREPLACE = [
    ('creator','author_norm'),
    ('subject','subject_all'), 
    ('title','title_unstemmed'), 
    ('swstitle','title_unstemmed'), 
    ('sub','subject_all'),
    ('addsrcid', 'test_matchkey_3'),
    ('cdate', 'publish_date')
    ]

FACET_MAP = { 'creator': 'author_facet',
              'tlevel':  'material_access',
              'rtype':   'material_content_type',
              # 'rtype':   'material_media_type',
              'lang':    'language',
              'topic':   'subject_all_facet',
              'library': 'consortium' }

FACET_PREFIX = 'facet_'
FACET_QUERY_PATTERN = ' *(AND NOT|AND) *facet_'
                 
CATALOGUE_MAP = {
    'DE-101': 'DNB / ZDB',
    'DE-576': 'BSZ Verbundkatalog',
    'DE-600': 'Zeitschriftendatenbank',
    'DE-601': 'GBV Verbundkatalog',
    'DE-602': 'KOBV Portal',
    'DE-603': 'hebis Verbundkatalog',
    'DE-604': 'BVB Verbundkatalog',
    'DE-605': 'HBZ Verbundkatalog',
    'DE-627': 'K10plus',
    'AT-OBV': 'OBV Verbundkatalog'
    }

SORT_MAP = {
    'screator': 'author_sort asc',
    'stitle':   'title_sort asc',
    'scdate':   'publish_date_sort desc', # Jahr absteigend
    'date2':    'publish_date_sort asc'   # Jahr aufsteigend
    }
    
# SOLR_QF      = 'title_unstemmed^400 author_norm^300 author_unstemmed^50 subject_worktitle^50 subject_topic^50 subject_geogname^100 subject_genre^50 subject_persname^100 subject_corpname^100 subject_meetname^100 subject_chrono^100 subject_all_norm^50 publish_date^200 publisher^50 allfields_unstemmed^10 summary^10 isbn^500 isbn_related^400'
SOLR_QF      = 'title_unstemmed^400 author_norm^300 author_unstemmed^50 subject_worktitle^50 subject_topic^50 subject_geogname^100 subject_genre^50 subject_persname^100 subject_corpname^100 subject_meetname^100 subject_chrono^100 subject_all_norm^50 publish_date^200 publisher^50 allfields^10 summary^10 isbn^500 isbn_related^400'
SOLR_DEFTYPE = 'edismax'
SOLR_MM      = '0%'
               
def Log(s):
    # print (s, file=sys.stderr)
    logging.info(s)

def rewrite_parameters(p_query, p_facet_query, p_sort, p_from, p_bulksize):
    try:
        p_from = int(p_from)-1
    except:
        p_from = 0

    try:
        p_bulksize = int (p_bulksize)
    except:
        p_bulksize = 5
        
    if p_bulksize > 50:
        p_bulksize = 50

    if p_query is None:   
        p_query = "Bauhaus Möbel"
    
    if (p_query[:4]=='(("(' or p_query[:4]=='(rid:("(') and p_query[-2:]=='))':
        p_query = 'id:%s' % p_query[2:-2]
        
    q_list = re.split(FACET_QUERY_PATTERN, p_query)
    p_query = q_list[0]
    Log('Split: %s %s' % (len(q_list),q_list))
    
    i = 2
    while i<len(q_list):
        Log('FQ:  %s  %s' % (q_list[i-1], q_list[i]))
        operator = q_list[i-1]
        [category,term] = q_list[i].split(':',2)
        if term[0] == '(':
            term = term[1:]
        if term[-1] == ')':
            term = term[:-1]
        
        try:
            category = FACETQUERY_MAP[FACET_PREFIX + category]
            # if category == 'material_media_type':
            if category == 'material_content_type':
                try:
                    term = MATERIAL_MEDIA_TYPE_MAP[term]
                except:
                    pass
            if operator == 'AND':
                p_facet_query.append('%s:%s' % (category,term))
                Log('%s:"%s"' % (category,term))
            elif operator == 'AND NOT':
                p_facet_query.append('-%s:%s' % (category,term))
                Log('-%s:"%s"' % (category,term))
        except:
            pass
        i=i+2
            
    #for (str, rpl) in FACETQUERYREPLACE:
    #    # Log("FACETQUERYREPLACE: %s -> %s" % (str,rpl))
    #    p_query = p_query.replace('%s:' % (str),'%s:'% (rpl))

    for (str, rpl) in QUERYREPLACE:
        # Log("QUERYREPLACE: %s -> %s" % (str,rpl))
        p_query = p_query.replace('%s:(' % (str),'%s:('% (rpl))

    try:
        p_sort = SORT_MAP[p_sort]
    except:
        p_sort = ""
        
    return p_query, p_facet_query, p_sort, p_from, p_bulksize

def clean_from_id(s):
    if s is not None:
        s = s.split(' (DE-')[0]
        s = s.split(' Verfasser')[0]
    return s
    
def remove_nonsort_characters(s, list=['\u009c','\u009C','\u0098']):
    t = ""
    for c in s:
        if c not in list:
            t = t + c
    return t
    

def marc_to_pnx(gvi_id, pnx_sourcerecordid, pnx_sourcesystem, pnx_recordid, 
                pnx_type, pnx_language, pnx_institutions, delcategory,
                link_templates, openurl_templates, baseurl_templates, isils, record, debug_flag):
    pnx_doc = { 
        "pnx": {
            "control": {
                "sourceid":["GVI"],
                "recordid":[pnx_recordid],
                "sourcerecordid":[pnx_sourcerecordid],
                "sourcesystem":[pnx_sourcesystem]
                },
            "display": {
                "type":[pnx_type],
                "source":["GVI"],
                # "language":pnx_language,
                },
            "delivery": {
                "fulltext":["no_fulltext"],
                # "delcategory":["Remote Search Resource"]
                # Special für Mannheim: keine delivery Section
                # "delcategory":["Structured Metadata"]
                "delcategory":["%s" % (delcategory)]
                },
            "links" : {
                "linktouc" : [ ],
                #"backlink" : [
                #    '$$Uhttp://gvi.bsz-bw.de/solrnewtest/GVITEST/select?q=id:%%22%s%%22$$DGVI' % gvi_id],
                "sourcerecord": [gvi_id]
                }
            }
        }

    for (link, text) in link_templates:
        link = link % gvi_id
        pnx_doc["pnx"]["links"]["linktouc"].append('$$U%s$$D%s' % (link, text))

    try:
        pnx_source=CATALOGUE_MAP[gvi_id[1:7]]
    except:
        pnx_source='GVI'
       
    Log("Record: %s\n" % record.as_json())
 
    for entry in record.physicaldescription:
        Log("pnx_format: %s" % entry)
    Log("pnx_creationdate: %s" % record.pubyear)
    Log("pnx_isbn: %s" % record.isbn)
    Log("pnx_issn: %s" % record.issn) 
 
    pnx_format       = '' # record.physicaldescription()
    pnx_creationdate = record.pubyear
    pnx_isbn         = record.isbn
    pnx_issn         = record.issn
	

    openurl_hash = {}
    ill_hash = {}
    acq_hash = {}
    
    pnx_subject_list     = []
    pnx_contributor_list = []
    pnx_ispartof_list    = []
    pnx_title_list       = []
    pnx_language_list    = []
    pnx_uri_list         = []
    
    pnx_uri_dict         = {}
    pnx_subject_dict     = {}
    
    pnx_creator   = None
    pnx_publisher = None
    pnx_thumbnail = None
    
    pnx_pages     = None

    for field in record.get_fields():
        Log('Field: %s' % field)
        if field.tag=='041' and 'a' in field:
                Log('working on 041 %s' % field['a'])
            #while field['a' in field:
                pnx_language_list.append(field['a']) 
                #field.delete_subfield('a')
                
        if field.tag=='100' and 'a' in field:
            pnx_creator  = clean_from_id(field['a'])
		
        if field.tag=='245' and 'a' in field:
            pnx_title_list.append(remove_nonsort_characters(field['a']))
            Log('pnx_title_list: %s' % pnx_title_list)
            if 'b' in field:
                pnx_title_list.append(remove_nonsort_characters(field['b']))
            
        if field.tag=='245' and 'a' in field:      
            title = field['a']
            if 'b' in field:
                title = "%s: %s" % (title, field['b'])
            pnx_title = remove_nonsort_characters(title)
		
        #if field.tag=='246' and field['a' in field:
        #    pnx_title_list.append(remove_nonsort_characters(field['a']))   

        if field.tag=="260" and pnx_publisher is None:
            if 'a' in field:
                pnx_publisher = field['a']
                ill_hash["EOrt"] = field['a']
                acq_hash["place"] = field['a']
            if 'b' in field:
                ill_hash["Verlag"] = field['b']
                if pnx_publisher is None:
                    pnx_publisher = field['b']
                else:
                    pnx_publisher = "%s : %s" % (pnx_publisher,field['b'])
            if 'c' in field:
                if pnx_creationdate is None:
                    pnx_creationdate = field['c'] 

        if field.tag=="264": # and pnx_publisher is None:
            if 'a' in field:
                pnx_publisher = field['a'] 
                ill_hash["EOrt"] = field['a']
                acq_hash["place"] = field['a']
            if 'b' in field:
                ill_hash["Verlag"] = field['b']
                if pnx_publisher is None:
                    pnx_publisher = field['b']
                else:
                    pnx_publisher = "%s : %s" % (pnx_publisher,field['b'])
            if 'c' in field:
                if pnx_creationdate is None:
                    pnx_creationdate = field['c'] 
                    
        if field.tag=="300": 
            if 'a' in field:
                pnx_pages = field['a']
        
        
        if field.tag in ['650', '655', '689'] and 'a' in field:
            keyword = field['a']
            if not keyword in pnx_subject_dict:
                pnx_subject_list.append(keyword)
                pnx_subject_dict[keyword] = 1
		
        if field.tag=='700' and 'a' in field:
            contributor = field['a']
            if 'e' in field:
                contributor = "%s (%s)" % (contributor, field['e'])
            pnx_contributor_list.append(contributor)
             
#        if field.tag=='773' and field['i'] is not None:
#            # Log('working on 773')
#            # if field['i'] == 'In':
#            if field['i'] is not None:
#                if 'in' in field['i'].lower():
#                    field.delete_subfield('i')
#                    while field['w'] is not None:
#                        field.delete_subfield('w')
#                    pnx_ispartof_list.append(field.format_field())   
#                    # pnx_ispartof_list.append(field.format_field()[3:])   
        
        if field.tag=='773' and (pnx_type == "article" or 'i' in field):
            if pnx_type == "article" or 'in' in field['i'].lower():
                while 'i' in field:
                    field.delete_subfield('i')
                while 'w' in field:
                    field.delete_subfield('w')
                while 't' in field:
                    pnx_ispartof_list.append(field['t']) 
                    field.delete_subfield('t')
                while 'g' in field:
                    tmpstr = field['g']
                    if tmpstr[:6] == 'pages:':
                        ill_hash["Seiten"] = tmpstr[6:]
                    else:
                        pnx_ispartof_list.append(field['g']) 
                    field.delete_subfield('g')

            
        if field.tag=='856' and 'q' in field  and 'u' in field and '3' in field:
            if field['q']=="image/gif" and field['3'].find("Katalogkarte")>=0:
                pnx_thumbnail="$$U%s" % field['u']       
        
        if field.tag=='856' and 'z' in field and 'u' in field:
            if field['z'].lower()=="kostenfrei":
                if 'x' not in field:
                    entry = "$$U%s$$DVolltext" % (field['u'])
                else:
                    entry = "$$U%s$$D%s (Volltext)" % (field['u'], field['x'])
                if not entry in pnx_uri_dict:
                    pnx_uri_list.append(entry)
                    pnx_uri_dict[entry] = 1
        
    pnx_identifier = None
    if pnx_isbn is not None:
        pnx_identifier = pnx_isbn
        # pnx_identifier = 'ISBN ' + pnx_isbn
    if pnx_identifier is None:
        if pnx_issn is not None:
            pnx_identifier = 'ISSN ' + pnx_issn
    else:
        if pnx_issn is not None:
            pnx_identifier = pnx_identifier + ' ISSN ' + pnx_issn
    
        
    pnx_description_list = []
    for id in ["501", "502", "505", "520"]:
        try:
            pnx_description_list.append(record[id].format_field())
        except:
            pass
            
    pnx_coverage = None
    try:
        pnx_coverage = record["362"].format_field()
    except:
        pass
    	
    pnx_edition = None
    try:
        pnx_edition = record["250"].format_field()
    except:
        pass   
    
# https://www2.bib.uni-mannheim.de/cgi-bin/fernleihe/index.pl?Isbn=3860225499&Titel=QUID&EJahr=1999    

# http://www.bib.uni-mannheim.de/cgi-bin/alma_infocenter/ill_alma.pl?&
# Titel={rft.btitle}&
# Titel={rft.title}&
# Issn={rft.issn}&
# Isbn={rft.isbn}&
# Verfasser={rft.aulast}&
# AufsatzAutor={rft.aulast}&
# EJahr={rft.date}&
# AufsatzTitel={rft.atitle}&
# sPage={rft.spage}&
# ePage={rft.epage}&
# Band={rft.volume}&
# Heft={rft.issue}&
# Bemerkung=Via+Primo&
# Versuch={rft.dcTitle}

    openurl_hash["rft_id"] = "info:gviid/%s" % (gvi_id)
    pnx_doc["pnx"]["display"]["source"] = [pnx_source]
    
    if pnx_isbn is not None:
        openurl_hash["rft.isbn"] = pnx_isbn
        ill_hash["Isbn"] = pnx_isbn
        acq_hash["isbnissn"] = pnx_isbn
    if pnx_issn is not None:
        openurl_hash["rft.issn"] = pnx_issn
        ill_hash["Issn"] = pnx_issn
        acq_hash["isbnissn"] = pnx_issn
        
    if pnx_language_list != []:
        pnx_doc["pnx"]["display"]["language"] = pnx_language_list    
    if pnx_title_list != []:
        pnx_doc["pnx"]["display"]["title"] = pnx_title_list   
        openurl_hash["rft.title"] = pnx_title_list[0]
        ill_hash["Titel"] = pnx_title_list[0]
        acq_hash["title"] = ill_hash["Titel"]
        
    if pnx_creator is not None:
        pnx_doc["pnx"]["display"]["creator"] = [pnx_creator]
        pnx_title_list[0]
        openurl_hash["rft.aulast"] = pnx_creator
        ill_hash["Verfasser"] = pnx_creator
        acq_hash["author"] = pnx_creator
        
    if pnx_subject_list != []:
        pnx_doc["pnx"]["display"]["subject"] = pnx_subject_list
        
    if pnx_ispartof_list != []:
        pnx_doc["pnx"]["display"]["ispartof"] = pnx_ispartof_list
        
    if pnx_publisher is not None:
        pnx_doc["pnx"]["display"]["publisher"] = [pnx_publisher]
        
    if pnx_creationdate is not None:
        pnx_doc["pnx"]["display"]["creationdate"] = [pnx_creationdate]
        openurl_hash["rft.date"] = pnx_creationdate
        ill_hash["EJahr"] = pnx_creationdate
        acq_hash["PublicationYear"] = pnx_creationdate
        
    if pnx_description_list != []:
        pnx_doc["pnx"]["display"]["description"] = pnx_description_list
        
    if pnx_identifier is not None:
        pnx_doc["pnx"]["display"]["identifier"] = [pnx_identifier]
    if pnx_coverage is not None:
        pnx_doc["pnx"]["display"]["coverage"] = [pnx_coverage]
    if pnx_edition is not None:
        pnx_doc["pnx"]["display"]["edition"] = [pnx_edition]
        openurl_hash["rft.edition"] = pnx_edition
        ill_hash["Auflage"] = pnx_edition
        
    if pnx_contributor_list != []:
        pnx_doc["pnx"]["display"]["contributor"] = pnx_contributor_list
        if pnx_creator is None:
            ill_hash["Verfasser"] = pnx_contributor_list[0]
            
    if pnx_thumbnail is not None:
        pnx_doc["pnx"]["links"]["thumbnail"] = [pnx_thumbnail]
    if pnx_uri_list != []:
        pnx_doc["pnx"]["links"]["linktorsrc"] = pnx_uri_list
        pnx_doc["pnx"]["delivery"]["fulltext"] = ["fulltext"]
    
    if pnx_pages is not None:
        ill_hash["Seiten"] = pnx_pages
        
    if pnx_type == "article":
        if ill_hash.get("Titel") is not None:
            ill_hash["AufsatzTitel"] = ill_hash["Titel"]
            del ill_hash["Titel"]
        if ill_hash.get("Verfasser") is not None:
            ill_hash["AufsatzAutor"] = ill_hash["Verfasser"]
            del ill_hash["Verfasser"]
            
        
    ill_hash["Bemerkung"] = "Via Primo/GVI %s" % gvi_id
    if pnx_ispartof_list != []:
        ill_hash["Bemerkung"] = ill_hash["Bemerkung"] + ", Enthalten in: %s" % (' '.join(pnx_ispartof_list))

    openurl_hash["ctx_enc"] = "info:ofi/enc:UTF-8"
    openurl_hash["ctx_ver"] = "Z39.88-2004"
    openurl_hash["url_ctx_fmt"] = "info:ofi/fmt:kev:mtx:ctx"
    openurl_hash["rfr_id"] = "info:sid/primo.exlibrisgroup.com-GVI"
    
    #pnx_openurl = "$$U%s?%s$$DOpenURL" % (openurl_base, urlencode(openurl_hash))
    #pnx_doc["pnx"]["links"]["openurl"] = [ pnx_openurl]
    #pnx_doc["pnx"]["links"]["linktouc"].append(pnx_openurl)
    
    for (openurl_base, text) in baseurl_templates:
        Log ("openurl: %s , %s" % ( openurl_base, text))
        pnx_openurl = "$$U%s?%s$$D%s (OpenURL)" % (openurl_base, urlencode(openurl_hash), text)
        pnx_doc["pnx"]["links"]["linktouc"].append(pnx_openurl)

    Log ("linktouc: %s\n" % pnx_doc["pnx"]["links"]["linktouc"] )
    
    for item in pnx_uri_list:
        pnx_doc["pnx"]["links"]["linktouc"].append(item)
        

 

    # Institutions
    ISIL_Flag       = False
    CONSORTIUM_Flag = False
    DE_180_FLAG     = False

    LIBRARY_ISIL    = "DE-180"
    OPAC_URL_PREFIX = "https://primo.bib.uni-mannheim.de/primo-explore/search?search_scope=MAN_ALMA&vid=MAN_UB&query=any,contains,"

    CONSORTIUM_ISIL = "DE-576"
    CONSORTIUM_GVI_PREFIX="(DE-627)" 
    # CONSORTIUM_URL_PREFIX = "https://portal.kobv.de/redirect.do?type=opac&library=DE-576&plv=2&target="
    # CONSORTIUM_URL_PREFIX = "https://swb.bsz-bw.de/DB=2.1/PPNSET?INDEXSET=21&PPN="
    # CONSORTIUM_URL_PREFIX = "https://swb.bsz-bw.de/DB=2.1/PPNSET?PRS=HOL&HILN=888&INDEXSET=21&PPN="
    CONSORTIUM_URL_PREFIX = "https://swb.bsz-bw.de/DB=2.1/PPNSET?PRS=HOL&INDEXSET=21&PPN="

    Log('PNX Institutions: %s' % pnx_institutions)
    if debug_flag:
        pnx_doc["pnx"]["links"]["linktouc"].append("$$U%s$$DBestandsnachweise: %s  *kein Link* (nur als Debug Hilfe)" % ("", pnx_institutions))


    consortium_gvi_prefix_len = len(CONSORTIUM_GVI_PREFIX)
    consortium_id = ''
    
    if CONSORTIUM_ISIL in pnx_institutions:
        for institution in pnx_institutions:
            if institution[:consortium_gvi_prefix_len] == CONSORTIUM_GVI_PREFIX:
                CONSORTIUM_Flag = True
                consortium_id = institution[consortium_gvi_prefix_len:]
            
    if CONSORTIUM_Flag == True:
        for institution in pnx_institutions:
            for (isil, text) in isils:
                if institution == isil:
                    pnx_holding = "$$U%s%s$$D%s" % (OPAC_URL_PREFIX, consortium_id, text)
                    pnx_doc["pnx"]["links"]["linktouc"].append(pnx_holding)
                    ISIL_Flag = True
                    
    if CONSORTIUM_Flag == True and ISIL_Flag == False:
                    pnx_holding_consort = "$$U%s%s$$DZeige Regionale Bestände im SWB-Verbundkatalog / Regional Holdings" % (CONSORTIUM_URL_PREFIX, consortium_id)
                    pnx_doc["pnx"]["links"]["linktouc"].append(pnx_holding_consort)


    # Specials for DE-180 (UB Mannheim )
    # ----------------------------------
    for (isil, text) in isils:
        if isil == "DE-180": 
            DE_180_FLAG = True
            
    if ISIL_Flag == False and DE_180_FLAG == True:
        ill_base = "https://www2.bib.uni-mannheim.de/cgi-bin/fernleihe/index.pl"
        ill_text = "Klicken sie hier, um das Medium per Fernleihe zu bestellen / Request this title via Inter Library Loan"
        pnx_ill = "$$U%s?%s$$D%s" % (ill_base, urlencode(ill_hash), ill_text)
        pnx_doc["pnx"]["links"]["linktouc"].append(pnx_ill)

        acq_base = "https://www.bib.uni-mannheim.de/medien/anschaffungsvorschlag"
        acq_text = "Machen Sie einen Anschaffungsvorschlag / Acquisition Request"
        pnx_acq  = "$$U%s?%s$$D%s" % (acq_base, urlencode(acq_hash), acq_text)
        pnx_doc["pnx"]["links"]["linktouc"].append(pnx_acq)

    
    Log("")
    Log("------------------------------------------------------------")
    Log("")
    
    return pnx_doc


# -------------------------------------------------------
# -- Routes ---------------------------------------------
# -------------------------------------------------------    


# -----------------------------------------------------------------
# PLAIN API zum GVI
#
# Aufruf in wsgi.py:
#    @app.route('/plain')
# -----------------------------------------------------------------

def do_plain():
    _query    = request.args.get('query') 
    _from     = request.args.get('from')
    _bulksize = request.args.get('bulksize')
    _sort     = request.args.get('sort')
    _token    = request.args.get('token')

    Log('\n\n\nNew Request: %s \n-----------' % datetime.datetime.now() )
    Log("Query: %s\nFrom: %s\nBulksize: %s\nSort: %s\nToken: %s\n" % (_query, _from, _bulksize, _sort, _token))

    FQ = []
    T = []
    T.append("Primo query:   %s" % _query)

    _query, _facetquery, _sort, _from, _bulksize = rewrite_parameters(_query, FQ, _sort, _from, _bulksize)
    # _query, _facetquery, _from, _bulksize = rewrite_parameters(_query, [], _from, _bulksize)
    Log("After transform:\nQuery: %s\nFrom: %s\nBulksize: %s\nSort: %s\nToken: %s\n" % (_query, _from, _bulksize, _sort, _token))
    
    solr = pysolr.Solr(GVIURL, timeout=10)
    results = solr.search(_query, rows=_bulksize, start=_from,
               **{ 'group': 'true',                     # grouping ein
                   'group.field': 'test_matchkey_3',    #
                   'group.limit': 10,                   #
                   'group.ngroups': 'false',            #
                   # groups zaehlen 
                   'stats': 'true',
                   'stats.field': '{!cardinality=true}test_matchkey_3',
                   'sort' : _sort,
                   'fl' : '*,score',
                   'mm' : SOLR_MM,
                   'qf' : SOLR_QF,
                   'defType' : SOLR_DEFTYPE,
                   'shards.tolerant': 'true',
                   'fq' : _facetquery,
                   'q.op' : 'AND',
                   'facet' : 'true', 
                   'facet.limit' : 10, 
                   'facet.field' : FACET_MAP.values() } )
    

    T.append("Solr query:    %s" % _query)
    T.append("Start:         %s" % _from)
    T.append("Rows:          %s" % _bulksize)
    T.append("Total results: %s" % results.stats["stats_fields"]["test_matchkey_3"]["cardinality"])
    
    
    number = 0
    groups = results.grouped["test_matchkey_3"]["groups"]
    for groupedresult in groups:
        gvi_id_list = []
        institutions = []
        docnumber = 0
        for r in groupedresult["doclist"]["docs"]:
            gvi_id_list.append(r["id"])
            institutions = institutions + r["institution_id"]
        result = groupedresult["doclist"]["docs"][docnumber]
        numFound = groupedresult["doclist"]["numFound"]
        matchkey = groupedresult["groupValue"]
        gvi_id = result["id"]
        T.append("")
        T.append("Group: %s %s %s" % (matchkey, numFound, " ".join(gvi_id_list)) ) 
        T.append("%s  (%s)" % (result["id"], result["material_content_type"][0].lower()))
        marcxml  = result["fullrecord"]
        marcfile = io.StringIO(marcxml)
        reclist  = parse_xml_to_array(marcfile)
        record   = reclist[0]
        #T.append("%s" % record)
        T.append("%s %s" % ('LDR', record.leader))
        for field in record.get_fields():
            T.append("%s %s" % (field.tag, field))
            #if field.is_control_field():
            #    T.append("%s %s" % (field.tag, field.data))
            #else:
            #    T.append("%s %s" % (field.tag, " ".join(field.indicators + field.subfields)))
            #if field.tag=='856' and field['q']=="image/gif" and field['u']!=None and \
            #   field['3']!=None and field['3'].find("Katalogkarte")!=-1:
            #    T.append("%s %s" % ("***",  field['u']))
    resp = make_response("\n".join(T))
    resp.headers.set('Content-type', 'text/plain')
    return resp

# (_query_:"{+boost='recip(sub(2022,publish_date_sort))'}((selma stern))")



    
# -----------------------------------------------------------------
# JSON API zum GVI
#
# Aufruf in wsgi.py:
#    @app.route('/json')
# -----------------------------------------------------------------

def do_json():
    # try:
        Log('\n\n\nNew Request: %s \n-----------' % datetime.datetime.now() )
         # (title:(sea) OR subject:("water")) AND facet_lang:("fre") AND facet_pfilter:("books") AND facet_creationdate:[2014 TO 2019]
        if FLAG:
            _query    = '((flucht))'
            _from     = '1'
            _bulksize = '10'
            _sort     = 'rank'
            _token    = '19-airsb-test'
        else:
            _query    = request.args.get('query')
            _from     = request.args.get('from')
            _bulksize = request.args.get('bulksize')
            _sort     = request.args.get('sort')
            _token    = request.args.get('token')
            
        Log("InQuery: %s\nFrom: %s\nBulksize: %s\nSort: %s\nToken: %s\n" % (_query, _from, _bulksize, _sort, _token))


        config = Config(_token)
        link_templates = config.get_links()
        openurl_templates = config.get_openurls()
        baseurl_templates = config.get_baseurls()
        isils = config.get_isils()
        delcategory = config.get_delcategory()
        gviurl = config.get_gviurl()
        if gviurl != None:
            GVIURL = gviurl
        
        if not config.validate(_token):
            resp=make_response("{ }")
            resp.headers.set('Content-type', 'application/json')
            return resp
        
        FQ = ["-consortium:DE-627", 
              # "-consortium:\"DE-600\"", 
              # "-consortium:\"DE-101\"", 
              # "-consortium:\"DE-603\"",      # Hebis raus
              "-institution_id:UNDEFINED", # Überordnungen
              "-institution_id:DE-603",    # HEBIS Katalogkarten 
              "-id:\\(DE-602\\)edochu_*",
              "-id:\\(DE-602\\)kobvindex_JMB*",
              "-consortium:\"AT-OBV\"", 
              "-consortium:\"FL\"",     
              "-collection:\"HBZFIX\"",
              "-consortium:\"UNDEFINED\"", 
              #'{!collapse field=test_matchkey_3}', # collapse raus
              # "-allfields_unstemmed:Safari"]
              #"-allfields:Safari"
              ] + config.get_filters()
              
        _query, _facetquery, _sort, _from, _bulksize = rewrite_parameters(_query, FQ, _sort, _from, _bulksize)
        query = '''(_query_:"{+boost='recip(sub(2022,publish_date_sort),1,1000,1)'+boost='if(exists(query({!v=consortium:DE-576})),1,0.75)'}%s")''' % _query
        # _query = '''(%s +publish_date_sort -consortium:DE-603)^100''' % _query
        
        Log("After transform:\nTrQuery: %s\nF_Query;%s\nFrom: %s\nBulksize: %s\nSort: %s\nToken: %s\n" % (_query, _facetquery,_from, _bulksize, _sort, _token))
        
        solr = pysolr.Solr(GVIURL, timeout=30)
      
        # De-Duplication
        # _facetquery.append('{!collapse field=test_matchkey_3 }')
        # _facetquery.append('{!collapse field=test_matchkey_3 max=publish_date_sort}')
        
        
        results = solr.search(_query, rows=_bulksize, start=_from, 
               **{ 'group': 'true',                     # grouping ein
                   'group.field': 'test_matchkey_3',    #
                   'group.limit': 10,                   #
                   'group.ngroups': 'false',            #
                   # groups zaehlen 
                   'stats': 'true',
                   'stats.field': '{!cardinality=true}test_matchkey_3',
                   'sort' : _sort,
                   'fl' : '*,score',
                   'hl' : 'false',
                   'mm' : SOLR_MM,
                   'qf' : SOLR_QF,
                   'spellcheck' : 'false',
                   'defType' : SOLR_DEFTYPE,
                   'shards.tolerant': 'true',
                   'fq' : _facetquery,
                   'q.op' : 'AND',
                   'facet' : 'true', 
                   'facet.mincount' : 1,
                   'facet.sort': 'count',
                   'facet.threads' : 4,
                   'facet.limit' : 10, 
                   'facet.field' : FACET_MAP.values() } )
      
        Log ("Matches: %s" % results.grouped["test_matchkey_3"]["matches"])      
        Log ("Stats:   %s" % results.stats["stats_fields"]["test_matchkey_3"]["cardinality"])      
      
        R = json.loads("""{}""")
        # R["info"]   = { "total":results.hits, "last":_from+len(results), "first":_from+1 }
        # R["info"]   = { "total":results.grouped["test_matchkey_3"]["matches"], "last":_from+len(results), "first":_from+1 }
        R["info"]   = { "total":results.stats["stats_fields"]["test_matchkey_3"]["cardinality"], "last":_from+len(results), "first":_from+1 }
        R["docs"]   = []
        R["facets"] = []
        
        Facets = R["facets"]
        
      
        
        for pnx_facet_name in FACET_MAP.keys():
            i=0
            facet_name = FACET_MAP[pnx_facet_name]
            Facets.append( { "name":pnx_facet_name, "values":[] })
            while i<len(results.facets["facet_fields"][facet_name]):
                value=results.facets["facet_fields"][facet_name][i]
                count=results.facets["facet_fields"][facet_name][i+1]
                if count>0 and (pnx_facet_name != 'facet_lang' or value != 'und'):
                    Facets[-1]["values"].append({"count":count, "value":value })
                i=i+2
        
        
        
        doclist = R["docs"]
        number = 0
        # for result in results:
        groups = results.grouped["test_matchkey_3"]["groups"]
        for groupedresult in groups:
            gvi_id_list = []
            pnx_institutions = []
            docnumber = 0
            for r in groupedresult["doclist"]["docs"]:
                gvi_id_list.append(r["id"])
                # if True:
                if "DE-576" in r["consortium"]:
                    # pnx_institutions.append(r["consortium"])
                    pnx_institutions.append("DE-576")
                    pnx_institutions.append(r["id"])
                    pnx_institutions = pnx_institutions + r["institution_id"]
            Log("result: %i" % number)
            # Log(result)
            result = groupedresult["doclist"]["docs"][docnumber]
            gvi_id = result["id"]
            pnx_sourcerecordid = gvi_id[8:]
            pnx_sourcesystem = gvi_id[1:3]+gvi_id[4:7]
            pnx_recordid = "%s_%s" % (pnx_sourcesystem, pnx_sourcerecordid)
            pnx_type     = result["material_content_type"][0].lower()
            pnx_language = result["language"][0].lower()
            marcxml  = result["fullrecord"]
            marcfile = io.StringIO(marcxml)
            reclist  = parse_xml_to_array(marcfile)
            record   = reclist[0]
            Log('Inst: %s' % pnx_institutions)
            doclist.append(marc_to_pnx(
                gvi_id, pnx_sourcerecordid, pnx_sourcesystem, pnx_recordid, pnx_type, 
                pnx_language, pnx_institutions, delcategory,
                link_templates, openurl_templates, baseurl_templates, isils,
                record,
                config._debug) )    
            # doclist.append(pnx_doc)    
            number = number + 1
        if FLAG:
            Log("\nPNX/json:\n%s" % R)
        else:
            resp = make_response(json.dumps(R, indent=2, sort_keys=True))
    #except:
            #resp=make_response("{ }")
            resp.headers.set('Content-type', 'application/json')
            return resp
    
if __name__ == "__main__":
    FLAG = True
    logging.basicConfig(
        stream=sys.stdout, 
        level=logging.DEBUG,
        # format='%(filename)s (line %(lineno)d) %(levelname)s %(asctime)s  %(message)s'
        format='%(filename)s (line %(lineno)d) %(levelname)s %(message)s'
    )
    do_json()

