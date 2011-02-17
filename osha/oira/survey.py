from five import grok
from osha.oira import model
from sqlalchemy import sql
from z3c.saconfig import Session
from euphorie.client import survey, report
import interfaces
from zope.i18n import translate

from cStringIO import StringIO
from rtfng.document.paragraph import Paragraph
from rtfng.Renderer import Renderer
from osha.oira import utils
from osha.oira import _

grok.templatedir("templates")

class OSHASurveyPublishTraverser(survey.SurveyPublishTraverser):
    phases = {
            "identification": interfaces.IOSHAIdentificationPhaseSkinLayer,
            "evaluation": interfaces.IOSHAEvaluationPhaseSkinLayer,
            "actionplan": interfaces.IOSHAActionPlanPhaseSkinLayer,
            "report": interfaces.IOSHAReportPhaseSkinLayer, }


class OSHAReportView(report.ReportView):
    """ Override the default view, to add a popup overlay
        asking the user if they want to participate in a survey. #2558

        See euphorie/client/survey.py for more info
    """
    grok.template("report")


class OSHAActionPlan(survey.ActionPlan):
    """
    Overrides the original ActionPlanReport in euphorie.client.survey.py
    to provide our own template.

    Please refer to original for more details.
    """
    grok.layer(interfaces.IOSHAActionPlanPhaseSkinLayer)
    grok.template("actionplan")



class OSHAActionPlanMixin():

    def _extra_updates(self):
        """ Provides the following extra attributes (as per #1517, #1518):
            - unanswered_risk_nodes
            - not_present_risk_nodes
            - unevaluated_nodes
            - evaluated_nodes

            Place in a separate method so that OSHAActionPlanReportDownload
            can call it.
        """
        if survey.redirectOnSurveyUpdate(self.request):
            return

        # I would have prefered to get the evaluated and unevaluated nodes via 
        # SQLAlchemy, but querying for action_plans (via any()) didn't seem 
        # to work, and in any case, a node might have an action plan that 
        # isn't fully populated yet!
        self.evaluated_nodes = utils.get_evaluated_nodes(self.nodes) 
        self.unevaluated_nodes = utils.get_unevaluated_nodes(self.nodes) 
        
        session=Session()
        query=session.query(model.SurveyTreeItem)\
                .filter(model.SurveyTreeItem.session==self.session)\
                .filter(sql.or_(model.MODULE_WITH_UNANSWERED_RISKS_FILTER,
                                model.UNANSWERED_RISKS_FILTER))\
                .order_by(model.SurveyTreeItem.path)
        self.unanswered_nodes=query.all()

        query=session.query(model.SurveyTreeItem)\
                .filter(model.SurveyTreeItem.session==self.session)\
                .filter(sql.or_(model.MODULE_WITH_RISKS_NOT_PRESENT_FILTER,
                                model.RISK_NOT_PRESENT_FILTER))\
                .order_by(model.SurveyTreeItem.path)
        self.risk_not_present_nodes=query.all()


class OSHAActionPlanReportView(report.ActionPlanReportView, OSHAActionPlanMixin):
    """
    Overrides the original ActionPlanReportView in euphorie.client.survey.py

    Provides the following extra attributes (as per #1517, #1518):
        unanswered_risk_nodes
        not_present_risk_nodes

    Please refer to original for more details.
    """
    grok.template("report_actionplan")
    grok.layer(interfaces.IOSHAReportPhaseSkinLayer)
    grok.name("view")
    download = False
    
    def title(self, node, zodbnode):
        if zodbnode.problem_description and zodbnode.problem_description.strip():
            return zodbnode.problem_description
        return node.title

    def update(self):
        """ """
        super(OSHAActionPlanReportView, self).update()
        self._extra_updates()

    def risk_status(self, node, zodbnode):
        """ """
        if node.postponed or not node.identification:
            return "unanswered"
        elif node.identification in [u"n/a", u"yes"]:
            return "not-present"
        elif node.identification == "no":
            if node.probability == 0:
                return "no-actionplans"
            elif node.action_plans == []:
                return "unevaluated"
            return "present"


class OSHAIdentificationReport(report.IdentificationReport):
    """
    Overrides the original IdentificationReport in euphorie.client.survey.py
    in order to provide a new template.

    Please refer to original for more details.
    """
    grok.layer(interfaces.IOSHAIdentificationPhaseSkinLayer)
    grok.template("report_identification")
    download = False


class OSHAActionPlanReportDownload(report.ActionPlanReportDownload, OSHAActionPlanMixin):
    """ Generate and download action report.
    """
    grok.layer(interfaces.IOSHAReportPhaseSkinLayer)
    grok.name("download")
    download =  True

    def update(self):
        """ Perform the super class' update and then get all the unanswered and
            non-present risks.
        """
        super(OSHAActionPlanReportDownload, self).update()

        session=Session()
        if self.session.company is None:
            self.session.company=model.Company()
        query=session.query(model.SurveyTreeItem)\
                .filter(model.SurveyTreeItem.session==self.session)\
                .filter(sql.not_(model.SKIPPED_PARENTS))\
                .filter(sql.or_(model.MODULE_WITH_RISK_OR_TOP5_FILTER,
                                model.RISK_PRESENT_OR_TOP5_FILTER))\
                .order_by(model.SurveyTreeItem.path)
        self.nodes=query.all()

        self._extra_updates()


    def addReportNodes(self, document, nodes, heading):
        """ """
        survey=self.request.survey
        t=lambda txt: translate(txt, context=self.request)
        section = report.createSection(document, self.context, self.request)
        section.append(
                    Paragraph( document.StyleSheet.ParagraphStyles.Heading1, 
                               heading)
                    )

        normal_style = document.StyleSheet.ParagraphStyles.Normal
        comment_style = document.StyleSheet.ParagraphStyles.Comment
        warning_style = document.StyleSheet.ParagraphStyles.Warning
        measure_heading_style = document.StyleSheet.ParagraphStyles.MeasureHeading
        header_styles = {
                0: document.StyleSheet.ParagraphStyles.Heading2,
                1: document.StyleSheet.ParagraphStyles.Heading3,
                2: document.StyleSheet.ParagraphStyles.Heading4,
                3: document.StyleSheet.ParagraphStyles.Heading5,
                }

        for node in nodes:
            zodb_node = survey.restrictedTraverse(node.zodb_path.split("/"))
            if node.type == 'risk':
                title = zodb_node.problem_description
            else:
                title = node.title
            section.append(
                    Paragraph(
                        header_styles[node.depth], 
                        u"%s %s" % (node.number, title)
                        )
                    )

            if node.type!="risk":
                continue

            if node.priority:
                if node.priority=="low":
                    level=_("report_priority_low", default=u"low priority risk")
                elif node.priority=="medium":
                    level=_("report_priority_medium", default=u"medium priority risk")
                elif node.priority=="high":
                    level=_("report_priority_high", default=u"high priority risk")
                section.append(Paragraph(normal_style, 
                    t(_("report_priority", default=u"This is a ")), t(level)))

            if node.comment and node.comment.strip():
                section.append(Paragraph(comment_style, node.comment))

            for (idx, measure) in enumerate(node.action_plans):
                if not measure.action_plan:
                    continue
                    
                if len(node.action_plans)==1:
                    section.append(Paragraph(measure_heading_style,
                        t(_("header_measure_single", default=u"Measure"))))
                else:
                    section.append(Paragraph(measure_heading_style,
                        t(_("header_measure", default=u"Measure ${index}", mapping={"index": idx+1}))))
                self.addMeasure(document, section, measure)
 


    def render(self):
        """ Mostly a copy of the render method in euphorie.client, but with
            some changes to also show unanswered risks and non-present risks.
            #1517 and #1518
        """
        document=report.createDocument()

        # XXX: This part is removed
        # self.addActionPlan(document)

        # XXX: and replaced with this part:
        heading = translate(
                _(  "header_present_risks", 
                    default=u"Risks that have been identified, evaluated and have an Action Plan:"),
                self.request)
        self.addReportNodes(document, self.evaluated_nodes, heading)

        heading = translate(
                _(  "header_unevaluated_risks", 
                    default=u"Risks that have been identified but NOT evaluated and do NOT have an Action Plan:"), 
                self.request)
        self.addReportNodes(document, self.unevaluated_nodes, heading)

        heading = translate(
                _(  "header_unanswered_risks",
                    default=u'Risks that have been "parked" and are still to be dealt with:'), 
                self.request)
        self.addReportNodes(document, self.unanswered_nodes, heading)
        
        heading = translate(
                _(  "header_risks_not_present",
                    default=u"Risks that are not present in your organisation:"), 
                self.request)
        self.addReportNodes(document, self.risk_not_present_nodes, heading)
        # Until here...

        renderer=Renderer()
        output=StringIO()
        renderer.Write(document, output)

        filename=_("filename_report_actionplan",
                   default=u"Action plan ${title}",
                   mapping=dict(title=self.session.title))
        filename=translate(filename, context=self.request)
        self.request.response.setHeader("Content-Disposition",
                            "attachment; filename=\"%s.rtf\"" % filename.encode("utf-8"))
        self.request.response.setHeader("Content-Type", "application/rtf")
        return output.getvalue()

