# ---------------------------------------
# PNX2GVI -- Map Primo Search To GVI Solr
# Autor: Stefan Lohrum <lohrum@zib.de>
# Version:  22.06.2020
# ---------------------------------------


from flask import Flask, make_response, request
from pymarc import Record, Field, parse_xml_to_array
from urllib.parse import urlencode
import pysolr, pymarc, io, json, sys, re, traceback, datetime

app    = Flask(__name__)
GVIURL = 'SECRETURL'

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
    ('Title','title_slim'), 
    ('swstitle','title_slim'), 
    ('sub','subject_all')
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
                 
               
SOLR_QF      = 'title_slim^400 author_norm^300 author_unstemmed^50 subject_worktitle^50 subject_topic^50 subject_geogname^100 subject_genre^50 subject_persname^100 subject_corpname^100 subject_meetname^100 subject_chrono^100 subject_all_norm^50 publish_date^200 publisher^50 allfields_unstemmed^10 summary^10 isbn^500 isbn_related^400'
SOLR_DEFTYPE = 'edismax'
SOLR_MM      = '0%'
               
def Log(s):
    print (s, file=sys.stderr)

def rewrite_parameters(p_query, p_facet_query, p_from, p_bulksize):
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
            
    for (str, rpl) in QUERYREPLACE:
        # Log("QUERYREPLACE: %s -> %s" % (str,rpl))
        p_query = p_query.replace('%s:(' % (str),'%s:('% (rpl))

    return p_query, p_facet_query, p_from, p_bulksize

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
    

def marc_to_pnx(gvi_id, pnx_sourcerecordid, pnx_sourcesystem, pnx_recordid, pnx_type, pnx_language, record):
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
                "delcategory":["Remote Search Resource"]
                },
            "links" : {
                "linktorequest" : [
                    '$$Uhttps://fernleihe.bosstest.bsz-bw.de/Record/%s$$DBOSS-BSZ-Fernleihe' % gvi_id],
                "linktosrc" : [
                    '$$Uhttps://portaltest.kobv.de/uid.do?index=gvi&query=%s$$DKOBV-Portal'    % gvi_id],
                "sourcerecord": [gvi_id]
                }
            }
        }
    
    
    pnx_format       = record.physicaldescription()
    pnx_creationdate = record.pubyear()
    pnx_isbn         = record.isbn()
    pnx_issn         = record.issn()
    
     
    pnx_subject_list     = []
    pnx_contributor_list = []
    pnx_ispartof_list    = []
    pnx_title_list       = []
    pnx_language_list    = []
	
    pnx_subject_dict     = {}

    
    pnx_creator  = None
    pnx_thumbnail=None
    for field in record.get_fields():
        
        if field.tag=='041' and field['a'] is not None:
                Log('working on 041 %s' % field['a'])
            #while field['a'] is not None:
                pnx_language_list.append(field['a']) 
                #field.delete_subfield('a')
                
        if field.tag=='100' and field['a'] is not None:
            pnx_creator  = clean_from_id(field['a'])
		
        if field.tag=='245' and field['a'] is not None:
            pnx_title_list.append(remove_nonsort_characters(field['a']))
            if field['b'] is not None:
                pnx_title_list.append(remove_nonsort_characters(field['b']))
            
        if field.tag=='245' and field['a'] is not None:            
            title = field['a']
            if field['b'] is not None:
                title = "%s: %s" % (title, field['b'])
            pnx_title = remove_nonsort_characters(title)
		
        if field.tag=='246' and field['a'] is not None:
            pnx_title_list.append(remove_nonsort_characters(field['a']))   
            
        if field.tag in ['650', '655', '689'] and field['a'] is not None:
            keyword = field['a']
            if keyword in pnx_subject_dict:
                pass
            else:
                pnx_subject_list.append(keyword)
                pnx_subject_dict[keyword] = 1
		
        if field.tag=='700' and field['a'] is not None:
            contributor = field['a']
            if field['e'] is not None:
                contributor = "%s (%s)" % (contributor, field['e'])
            pnx_contributor_list.append(contributor)
             
        if field.tag=='773' and field['i'] is not None:
            Log('working on 773')
            if field['i'] == 'In':
                field.delete_subfield('i')
                while field['w'] is not None:
                    field.delete_subfield('w')
                pnx_ispartof_list.append(field.format_field())   
                # pnx_ispartof_list.append(field.format_field()[3:])   
            
        if field.tag=='856' and field['q']=="image/gif" and field['u'] is not None and \
        field['3'] is not None and field['3'].find("Katalogkarte")>=0:
            pnx_thumbnail="$$U%s" % field['u']       

        
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
    
        
    pnx_description = None
    try:
        pnx_description = record["520"].format_field()
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
	
    pnx_publisher = None
    try:
        pnx_publisher = record["260"].format_field()
    except:
        pass
	
    pnx_openurl = urlencode({"rft_id": "info:gviid/%s" % (gvi_id)})
	
    if pnx_language_list != []:
        pnx_doc["pnx"]["display"]["language"] = pnx_language_list    
    if pnx_title_list != []:
        pnx_doc["pnx"]["display"]["title"] = pnx_title_list    
    if pnx_creator is not None:
        pnx_doc["pnx"]["display"]["creator"] = [pnx_creator]
    if pnx_subject_list != []:
        pnx_doc["pnx"]["display"]["subject"] = pnx_subject_list
    if pnx_ispartof_list != []:
        pnx_doc["pnx"]["display"]["ispartof"] = pnx_ispartof_list
    if pnx_publisher is not None:
        pnx_doc["pnx"]["display"]["publisher"] = [pnx_publisher]
    if pnx_creationdate is not None:
        pnx_doc["pnx"]["display"]["creationdate"] = [pnx_creationdate]
    if pnx_identifier is not None:
        pnx_doc["pnx"]["display"]["identifier"] = [pnx_identifier]
    if pnx_description is not None:
        pnx_doc["pnx"]["display"]["description"] = [pnx_description]
    if pnx_coverage is not None:
        pnx_doc["pnx"]["display"]["coverage"] = [pnx_coverage]
    if pnx_edition is not None:
        pnx_doc["pnx"]["display"]["edition"] = [pnx_edition]
    if pnx_contributor_list != []:
        pnx_doc["pnx"]["display"]["contributor"] = pnx_contributor_list
    if pnx_thumbnail is not None:
        pnx_doc["pnx"]["links"]["thumbnail"] = [pnx_thumbnail]
    if pnx_openurl is not None:
        pnx_doc["pnx"]["links"]["openurl"] = [pnx_openurl]
    return pnx_doc
    


@app.route('/json')

def do_json():
    # try:
        Log('\n\n\nNew Request: %s \n-----------' % datetime.datetime.now() )
         # (title:(sea) OR subject:("water")) AND facet_lang:("fre") AND facet_pfilter:("books") AND facet_creationdate:[2014 TO 2019]
        _query    = request.args.get('query')
        _from     = request.args.get('from')
        _bulksize = request.args.get('bulksize')
        _sort     = request.args.get('sort')
        _token    = request.args.get('token')
        
        Log("InQuery: %s\nFrom: %s\nBulksize: %s\nSort: %s\nToken: %s\n" % (_query, _from, _bulksize, _sort, _token))
                   
        FQ = ["-consortium:DE-101", "-consortium:DE-600", "-consortium:DE-101", 
              "-consortium:DE-627", "-consortium:DE-600", "-consortium:UNDEFINED",  
              "-allfields_unstemmed:Safari"]
        _query, _facetquery, _from, _bulksize = rewrite_parameters(_query, FQ, _from, _bulksize)
        Log("After transform:\nTrQuery: %s\nF_Query;%s\nFrom: %s\nBulksize: %s\nSort: %s\nToken: %s\n" % (_query, _facetquery,_from, _bulksize, _sort, _token))
        
        solr = pysolr.Solr(GVIURL, timeout=10)
      
        # De-Duplication
        # _facetquery.append('{!collapse field=test_matchkey_3 }')
        # _facetquery.append('{!collapse field=test_matchkey_3 max=publish_date_sort}')
        
        
        results = solr.search(_query, rows=_bulksize, start=_from, 
               **{ #'group': 'true',
                   #'group.field': 'test_matchkey_3',
                   #'group.limit': 10,
                   #'group.ngroups': 'false',
                   'mm' : SOLR_MM,
                   'qf' : SOLR_QF,
                   'defType' : SOLR_DEFTYPE,
                   'shards.tolerant': 'true',
                   'fq' : _facetquery,
                   'q.op' : 'AND',
                   'facet' : 'on', 
                   'facet_limit' : 10, 
                   'facet.field' : FACET_MAP.values() } )
        
        R = json.loads("""{}""")
        R["info"]   = { "total":results.hits, "last":_from+len(results), "first":_from+1 }
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
        for result in results:
            Log("result: %i" % number)
            # Log(result)
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
            
            doclist.append(marc_to_pnx(gvi_id, pnx_sourcerecordid, pnx_sourcesystem, pnx_recordid, pnx_type, pnx_language, record) )    
            # doclist.append(pnx_doc)    
            number = number + 1

        # Log("\nPNX/json:\n%s" % R)
        resp = make_response(json.dumps(R, indent=2, sort_keys=True))
    #except:
        #resp=make_response("{ }")
        resp.headers.set('Content-type', 'application/json')
        return resp
    
