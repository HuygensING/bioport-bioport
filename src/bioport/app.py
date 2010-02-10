import datetime
import grok
import os
import random
import zope.interface
from chameleon.zpt.template import PageTemplateFile
from common import format_date, format_dates, format_number, html2unicode, maanden
from NamenIndex.common import to_ymd
from plone.memoize import ram
from plone.memoize.instance import memoize
from time import time
from z3c.batching.batch import Batch

def _request_data_cachekey(method, self):
    return self.request.form
    
class RepositoryView:
    def repository(self):
        principal = self.request.principal
        user = principal and principal.id
        return self.context.repository(user=user)
    
    def get_sources(self):
        return self.repository().get_sources()
    
    def get_person(self,bioport_id):
        return self.repository().get_person(bioport_id)
    
    def get_status_values(self, k=None):
        return self.repository().get_status_values(k)
    

    
    @ram.cache(lambda *args: time() // (60 * 60))
    def count_persons(self):
        #XXX cache this
        i = self.repository().db.count_persons()
        i = format_number(i)
        return i
    
    @ram.cache(lambda *args: time() // (60 * 60))
    def count_biographies(self):
        try:
            return self.context._count_biographies
        except AttributeError:
            i = self.repository().db.count_biographies()
            #XXX turned of caching, need to find some "update once a day" solution
            i = format_number(i)
            return i
            self.context._count_biographies = format_number(i)
        return self.context._count_biographies
       
    def menu_items(self):
        return [
                (self.application_url(), 'home'),
                (self.url('zoek'), 'zoeken'),
                (self.url('personen', data={'beginletter':'a'}), 'bladeren'),
                (self.url('about'), 'project'),
                (self.url('blog'), 'blog'),
                (self.url('agenda'), 'agenda'),
#                (self.url('colofon'), 'colofon'),
                (self.url('links'), 'links'),
                (self.url('faq'), 'faq'),
                (self.url('contact'), 'contact'),
#                (self.url('english'), 'english'),
        ]    
    def today(self):
        today = datetime.date.today()
        month = maanden[today.month-1]
        return '%s %s' % (today.day, month)    
    
class Batcher: 
    def update(self, **kw):
        self.start = int(self.request.get('start', 0))
        self.size = int(self.request.get('size', 30))
        
    def batch_url(self, start=None, size=None):
        data = self.request.form
        if start != None:
            data['start'] = start
        if size != None:
            data['size'] = size
        return self.url(data= data)    
 
class Bioport(grok.Application, grok.Container):
              
    SVN_REPOSITORY = None
    SVN_REPOSITORY_LOCAL_COPY = None
    DB_CONNECTION = None
    debug=False
    def __init__(self, db_connection=None):
        super(Bioport,self).__init__() #cargoculting from ingforms 
        from admin import Admin
        self['admin'] = Admin()
        self['admin'].DB_CONNECTION = db_connection
    
    def format_dates(self, s1, s2, **args):
        return  format_dates(s1, s2, **args)

    def repository(self, user):
        return self['admin'].repository(user=user)
    def format_number(self, s):
        return format_number(s)

#    
class BioPortTraverser(object):
    
    #CODE for construction traverse_subpath from 
    #  http://grok.zope.org/documentation/how-to/traversing-subpaths-in-views 

    def publishTraverse(self, request, name):
       self._traverse_subpath = request.getTraversalStack() + [name]
       request.setTraversalStack([])
       return self 
    def traverse_subpath(self):
       return getattr(self, '_traverse_subpath', [])
       
    def traverse_subpath_helper(self, i, default=None):
        p = self.traverse_subpath()
        if i < len(p):
            return p[i]
        else:
            return default   
        
class Index(grok.View, RepositoryView):
    pass

class Popup_Template(grok.View):
    #make the main template avaible for everything
    grok.context(zope.interface.Interface)
    
class Main_Template(grok.View, RepositoryView):
    #make the main template avaible for everything
    grok.context(zope.interface.Interface)

class Admin_Template(grok.View):
    #make the main template avaible for everything
    grok.context(zope.interface.Interface)   

class SiteMacros(grok.View):
    grok.context(zope.interface.Interface)   
    
class Personen(BioPortTraverser,grok.View,RepositoryView, Batcher):
    
    def update(self):
        Batcher.update(self)
    @memoize
    def get_persons(self):
        # XXX get_ method with side effects braks least astonishment principle
        qry = {}
        #request.form has unicode keys - make strings
        for k in [
            'bioport_id', 
            'beginletter',
            'category',
            'geboortejaar_min',
            'geboortejaar_max',
            'geslacht',
#        has_illustrations=None, #boolean: does this person have illustrations?
#        is_identified=None,
            'order_by', 
            'search_term',
            'search_name',
            'size',
            'source_id',
            'start',
            'status',
            'sterfjaar_min', 
            'sterfjaar_max',
#        start=None,
#        size=None,
             ]:
            if k in self.request.keys():
                qry[k] = self.request[k]
        repository = self.repository()
        persons = repository.get_persons_sequence(**qry)
        batch = Batch(persons,  start=self.start, size=self.size)
        self.qry = qry
        batch.grand_total = len(persons)
        self.batch = batch
        return batch

    def search_description(self):
        """return a description for the user of the search parameters in the request"""
        result= ''
        request = self.request
        if request.get('search_term'):
            result += 'met het woord <em>%s</em> in de tekst' % request.get('search_term')
        if request.get('search_name'):
            result += 'met het woord <em>%s</em> in de naam van de persoon' % request.get('search_name')
        if result:
            result = 'U zocht naar personen ' + result
        return result
    def batch_navigation(self, batch):
        return '<a href="%s">%s</a>' % (self.batch_url(start=batch.start), batch[0].naam().geslachtsnaam())

    @ram.cache(_request_data_cachekey)
    def navigation_box_data(self):
        """  This function returns a list of 3-tuples representing pages
             of paged results. They have the form
             (url of a page, first name on that page, last name on that page)
        """ 
        ls = []
        for batch in self.batch.batches:
            url = self.batch_url(start=batch.start)
            n1 = batch[0].naam()
            n1 = n1 and n1.geslachtsnaam()
            n2 = batch[-1].naam()
            n2 = n2 and n2.geslachtsnaam()
            ls.append((url, n1, n2))
        return ls

    def get_navigation_box(self):
        "This function returns the html for the navigation box"
        template_filename = os.path.join(
                      os.path.dirname(__file__),
                      'app_templates',
                      'navigation_block.cpt')
        template = PageTemplateFile(template_filename)
        return template(view=self, request=self.request)
        return "Navigation box"
    
class Persoon(BioPortTraverser, grok.View,RepositoryView): #, BioPortTraverser):
    def update(self, **args):
        self.bioport_id = self.traverse_subpath_helper(0) or self.request.get('bioport_id')
        redirects_to = self.repository().redirects_to(self.bioport_id)
        if redirects_to:
            self.bioport_id = redirects_to
        if not self.bioport_id:
            self.bioport_id = random.choice(self.repository().get_bioport_ids())
            self.redirect(self.url(self) + '/'+ self.bioport_id)
        self.person  = self.repository().get_person(bioport_id=self.bioport_id) 
        self.biography  = self.merged_biography = self.person.get_merged_biography()

    def get_event(self, type, biography=None):
        if not biography:
            biography = self.merged_biography
        event_el = biography.get_event(type)
        if event_el is not None:
            #we construct a convenient object
            class EventWrapper:
                def __init__(self, el):
                    self.when = el.get('when')
                    self.when_ymd = to_ymd(self.when) 
                    self.when_formatted = format_date(self.when)
                    self.notBefore = el.get('notBefore')
                    self.notBefore_ymd = to_ymd(self.notBefore) 
                    self.notBefore_formatted = format_date(self.notBefore)
                    self.notAfter = el.get('notAfter')
                    self.notAfter_ymd = to_ymd(self.notAfter) 
                    self.notAfter_formatted = format_date(self.notAfter)
                    self.date_text = el.find('date') is not None and el.find('date').text or ''
                    self.place =  el.find('place') is not None and el.find('place').text or ''
                    self.place_id = el.get('place_id')
                    self.type = el.get('type')
            return EventWrapper(event_el)
        else:
            return None      
    
    def get_states(self,type, biography=None):
        if not biography:
            biography = self.merged_biography
        result = []
        for el in  biography.get_states(type):
            if el is not None:
                class StateWrapper:
                    def __init__(self, el):
                        self.frm = el.get('from')
                        self.frm_ymd  = to_ymd(self.frm)
                        self.to = el.get('to')
                        self.to_ymd = to_ymd(self.to)
                        self.type = type
                        self.place = el.find('place') is not None and el.find('place').text or ''
                        self.text = el.text
                        self.idno = el.get('idno')
                        self.element = el
                    def has_content(self):
                        if self.frm or self.to or self.text or self.place or self.idno:
                            return True
                        else:
                            return False
                result.append(StateWrapper(el))
        return result
    def get_state(self, type, biography=None):
        states = self.get_states(type, biography)
        if states:
            return states[0]
        
    def maanden(self):
        return maanden
    
class Zoek(grok.View, RepositoryView):
    pass


class Auteurs(grok.View,RepositoryView, Batcher):
    def update(self):
        Batcher.update(self)
    def get_auteurs(self, **args):

        d = {}
        #request.form has unicode keys - make strings
        for k in self.request.form:
            d[str(k)] = self.request.form[k]
        
        ls = self.repository().get_authors(**d) 
        
        batch = Batch(ls, start=self.start, size=self.size)
        batch.grand_total = len(ls)
        return batch



class Bronnen(grok.View, RepositoryView):
    pass
class Colofon(grok.View, RepositoryView):
    pass

class Birthdays_Box(grok.View, RepositoryView):
    def get_persons(self):
        #get the month and day of today
        today = datetime.date.today().strftime('-%m-%d')
        #query the database for persons born on this date
        persons = self.repository().get_persons(where_clause='geboortedatum like "____%s"' % today, has_illustrations=True)
        if len(persons) < 3:
            #if we have less then 3 people, we cheat a bit and take someone who died today
            persons += self.repository().get_persons(where_clause='sterfdatum like "____%s"' % today, has_illustrations=True)
             
        return persons[:3]

class Birthdays(grok.View, RepositoryView):
    def get_persons_born_today(self):
        #get the month and day of today
        today = datetime.date.today().strftime('-%m-%d')
        #query the database for persons born on this date
        persons = self.repository().get_persons(where_clause='geboortedatum like "____%s"' % today)
        return persons

    def get_persons_dead_today(self):
        #get the month and day of today
        today = datetime.date.today().strftime('-%m-%d')
        #query the database for persons born on this date
        persons = self.repository().get_persons(where_clause='sterfdatum like "____%s"' % today)
        return persons
    

    
class About(grok.View, RepositoryView):
    pass

class Agenda(grok.View, RepositoryView):
    pass

class English(grok.View, RepositoryView):
    pass
class FAQ(grok.View, RepositoryView):
    pass
class Images_XML(grok.View, RepositoryView):
    grok.name('images.xml')
#    @ram.cache(lambda *args: time() // (60 * 60 * 24))
    def render(self):
        self.request.response.setHeader('Content-Type', 'text/xml')
        
        persons = self.repository().get_persons(has_illustrations=True, order_by='random', size=20)
        
        result = """<?xml version="1.0"?><root>"""
        for person in persons:
            illustrations = person.get_merged_biography().get_illustrations()
            if not illustrations:
                #if the database is up to date, it should not happen that we find persons without an illustration
                #as a result of a call to get_persons(has_illustrations=True)
                #but it can happen ...
                continue
            illustration = illustrations[0]
            result += '<image src="%s" title="%s" url="%s/%s" />\n' % (
                           illustration.cached_url(), 
#                           urllib.quote(unicode( person.name()).encode('utf8')), 
                           html2unicode(unicode(person.name())),
                           self.url('persoon'),
                           person.bioport_id,
                           )
        result += '</root>'
        return result

class BelowBios(grok.ViewletManager):
    grok.name('belowbios')
    grok.context(Bioport)
    
class Collecties(grok.View, RepositoryView):
    pass

class Instellingen(grok.View, RepositoryView):
    pass

class Stichting(grok.View, RepositoryView):
    pass

class RedactieRaad(grok.View, RepositoryView):
    pass

class Links(grok.View,RepositoryView):
    pass
class Blog(grok.View,RepositoryView):
    pass
