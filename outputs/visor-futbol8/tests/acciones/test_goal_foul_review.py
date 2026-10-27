import unittest
import cv2,numpy as np
from f8.acciones.sequence_engine import sequence_actions
from f8.acciones.automatic_fusion import enrich
from f8.acciones.visual_shots import search_windows
from f8.acciones.video_time import sample_video
from f8.publicacion.analytics_v3 import profiles_for


def proposal(label='Goal',time=.3,**kw):return {'class':label,'time':time,'score':.8,**kw}


def release_rows(kit='opponent',pid=None):
    rows=[]
    for i,x in enumerate([20,20,80,110,140]):
        actor={'id':1,'kit':kit,'player_id':pid,'box':[0,0,40,100],'position':None}
        rows.append({'time':i*.1,'frame':i,'tracks':[actor],'ball':{'center':[x,100],'confidence':.9,'position':None},'possession':{'track_id':1,'distance':.1} if i<2 else None})
    return rows


class GoalFoulReviewTests(unittest.TestCase):
    def test_opponent_goal_keeps_measured_actor_without_orange_name(self):
        es,_=sequence_actions(release_rows(pid='orange-7'),[proposal()],True)
        self.assertEqual(len(es),1);self.assertEqual(es[0]['team'],'opponent');self.assertEqual(es[0]['kind'],'goal');self.assertIsNone(es[0]['player_id']);self.assertEqual(es[0]['source_track'],1)
        self.assertEqual(es[0]['actor_evidence']['state'],'measured_release')
        p=profiles_for([],es,[{'jersey_number':7}],10)[0]
        self.assertEqual(p['metrics']['goals']['candidates'],0)

    def test_unknown_author_and_missing_ball_do_not_delete_goal(self):
        rows=release_rows('orange')
        for r in rows:r['ball']=None;r['possession']=None
        es,_=sequence_actions(rows,[proposal()],True)
        self.assertEqual(len(es),1);self.assertIsNone(es[0]['player_id']);self.assertEqual(es[0]['team'],'unresolved');self.assertEqual(es[0]['state'],'candidate')
        self.assertEqual(es[0]['actor_evidence']['state'],'unobserved')

    def test_anonymous_orange_release_keeps_team(self):
        es,_=sequence_actions(release_rows('orange'),[proposal()],True)
        self.assertEqual(es[0]['team'],'orange');self.assertIsNone(es[0]['player_id'])

    def test_adjacent_identity_handoff_is_not_used_to_name_scorer(self):
        from f8.acciones.pass_engine import contact_episodes
        from f8.identidad.identity_recovery import camera_offsets
        from f8.acciones.sequence_engine import released_actor
        rows=release_rows('orange','orange-7');contacts=contact_episodes(rows,True)
        contacts[0]['contact_identity_evidence']={'player_id':'orange-7','support':[]}
        actor,evidence=released_actor(contacts,rows,.3,camera_offsets(rows))
        self.assertIsNone(actor['player_id']);self.assertEqual(evidence['state'],'measured_release')

    def test_ambiguous_team_cannot_keep_orange_identity(self):
        es,_=sequence_actions(release_rows('uncertain','orange-7'),[proposal()],True)
        self.assertEqual(es[0]['team'],'unresolved');self.assertIsNone(es[0]['player_id'])

    def test_non_goal_shot_and_visual_approach_never_become_goal(self):
        for label in ('Shots off target','Shots on target','Visual goal approach'):
            es,_=sequence_actions([], [proposal(label)],True)
            self.assertEqual(es[0]['kind'],'shot');self.assertEqual(es[0]['state'],'candidate')

    def test_goal_shot_duplicates_preserve_evidence_and_context(self):
        es,_=sequence_actions([], [proposal('Shots on target',10),proposal('Goal',10.4),proposal('Visual goal approach',10.2,goal_end=0)],True)
        self.assertEqual(len(es),1);self.assertEqual(es[0]['kind'],'goal');self.assertEqual(len(es[0]['proposal_evidence']),3)
        self.assertLessEqual(es[0]['evidence_start'],5);self.assertGreaterEqual(es[0]['evidence_end'],22.4);self.assertIsNotNone(es[0]['visual_evidence'])

    def test_nearby_separate_goals_and_shots_are_preserved(self):
        es,_=sequence_actions([], [proposal(time=10),proposal(time=10.5),proposal('Shots on target',10.2)],True)
        self.assertEqual(sum(e['kind']=='goal' for e in es),2);self.assertEqual(len({e['id'] for e in es}),len(es))
        es,_=sequence_actions([], [proposal('Visual goal approach',10,goal_end=0),proposal('Visual goal approach',10,goal_end=100)],True)
        self.assertEqual(len(es),2);self.assertEqual(len({e['id'] for e in es}),2)

    def test_contact_is_not_a_confirmed_or_attributed_foul(self):
        rows=release_rows('orange','orange-7');es,_=sequence_actions(rows,[],True);self.assertFalse(any(e['kind'].startswith('foul') for e in es))
        es,_=sequence_actions(rows,[proposal('Foul')],True)
        self.assertEqual(es[0]['state'],'candidate');self.assertIsNone(es[0]['player_id']);self.assertIsNone(es[0]['foul_role']);self.assertIsNone(es[0]['committed_by']);self.assertIsNone(es[0]['received_by']);self.assertEqual(es[0]['decision_state'],'pending')

    def test_duplicate_fouls_preserve_evidence_without_merging_nearby_fouls(self):
        es,_=sequence_actions([], [proposal('Foul',10),proposal('Foul',10),proposal('Foul',10.5)],True)
        self.assertEqual(len(es),2);self.assertEqual(len(es[0]['proposal_evidence']),2)

    def test_kickoff_or_free_kick_support_does_not_confirm_event(self):
        es,_=sequence_actions([], [proposal('Goal',10),proposal('Kick-off',20),proposal('Foul',40),proposal('Direct free-kick',45)],True)
        self.assertEqual([len(e['complementary_evidence']) for e in es],[1,1]);self.assertTrue(all(e['event_validation']=='pending' for e in es))
        es,_=sequence_actions([], [proposal('Kick-off',20),proposal('Direct free-kick',45)],True);self.assertEqual(es,[])

    def test_wrong_timestamps_are_quarantined_with_original_evidence(self):
        invalid=[proposal(time=-1),proposal(time=float('nan')),proposal(time=11,source_duration=10),proposal(time=3,timestamp=7),proposal(time=3,evidence_start=4)]
        es,q=sequence_actions([],invalid,True);self.assertEqual(es,[]);self.assertEqual(len(q['rejected_proposals']),len(invalid))
        self.assertEqual(q['rejected_proposals'][3]['reason'],'timestamp_mismatch')
        import json
        json.dumps(q,allow_nan=False)

    def test_temporal_candidates_open_visual_windows_without_any_ball(self):
        self.assertEqual(search_windows([],60,[proposal(time=30)]),[[25,42]])
        self.assertEqual(search_windows([],60,[proposal('Foul',59)]),[[54,60]])

    def test_early_fusion_keeps_unattributed_events_too(self):
        es,_=enrich([],[],[proposal(),proposal('Foul',10)])
        self.assertEqual([e['kind'] for e in es],['goal','foul_committed']);self.assertTrue(all(e['player_id'] is None for e in es))


class FakeCapture:
    def __init__(self,times):self.times=times;self.index=-1
    def grab(self):self.index+=1;return self.index<len(self.times)
    def retrieve(self):return True,np.zeros((4,4,3),np.uint8)
    def set(self,key,value):self.setting=(key,value);return True
    def get(self,key):return self.times[self.index]*1000 if key==cv2.CAP_PROP_POS_MSEC else len(self.times) if key==cv2.CAP_PROP_FRAME_COUNT else 30


class PresentationTimeTests(unittest.TestCase):
    def test_explicit_encoded_orientation_disables_only_decoder_autorotation(self):
        cap=FakeCapture([0,.5]);_,times,_,q=sample_video(cap,orientation='encoded')
        self.assertEqual(cap.setting,(cv2.CAP_PROP_ORIENTATION_AUTO,0));self.assertEqual(times,[0,.5]);self.assertEqual(q['orientation'],'encoded')

    def test_full_video_sampling_uses_pts_including_variable_frame_rate(self):
        images,times,frames,q=sample_video(FakeCapture([0,.04,.49,.51,1.03,1.09,1.51]))
        self.assertEqual(times,[0,.51,1.03,1.51]);self.assertEqual(frames,[0,3,4,6]);self.assertEqual(len(images),4);self.assertTrue(q['full_source']);self.assertEqual(q['decoded_frames'],7)

    def test_missing_timestamp_does_not_silently_use_average_fps(self):
        with self.assertRaises(ValueError):sample_video(FakeCapture([0,0,.5]))
        with self.assertRaises(ValueError):sample_video(FakeCapture([0,float('nan')]))

    def test_limited_run_is_never_reported_as_full_video(self):
        _,times,_,q=sample_video(FakeCapture([0,.5,1,1.5]),limit=1)
        self.assertEqual(times,[0,.5]);self.assertFalse(q['full_source'])


class ReviewExportTests(unittest.TestCase):
    def run_export(self,stale=False,orientation_mismatch=False):
        import contextlib,io,json,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from f8.acciones.review_candidates import main
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.mov';source.write_bytes(b'synthetic-source');stat=source.stat()
            fp={'source':str(source.resolve()),'size':stat.st_size+(1 if stale else 0),'mtime_ns':stat.st_mtime_ns}
            (root/'temporal-candidates.json').write_text(json.dumps([proposal(time=3,timestamp=3)]),encoding='utf8')
            (root/'temporal-metadata.json').write_text(json.dumps({'source_fingerprint':fp,'status':'complete','full_source':True,'last_decoded_timestamp':9,'orientation':'encoded' if orientation_mismatch else 'display'}),encoding='utf8')
            args=['review_candidates','--source',str(source),'--duration','10','--temporal',str(root/'temporal-candidates.json'),'--output',str(root/'out')]
            if orientation_mismatch:args+=['--records',str(root/'absent-records.json')]
            with patch('sys.argv',args),contextlib.redirect_stdout(io.StringIO()):main()
            actions=json.loads((root/'out/actions.json').read_text(encoding='utf8'));intervals=json.loads((root/'out/review-intervals.json').read_text(encoding='utf8'))
            self.assertEqual(actions[0]['team'],'unresolved');self.assertIsNone(actions[0]['player_id']);self.assertEqual(intervals[0]['end'],10)

    def test_isolated_export_preserves_unattributed_event_and_source_bounds(self):self.run_export()
    def test_stale_source_proposals_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'another source'):self.run_export(stale=True)
    def test_mismatched_coordinate_orientation_is_rejected_before_reading_records(self):
        with self.assertRaisesRegex(ValueError,'same orientation'):self.run_export(orientation_mismatch=True)


if __name__=='__main__':unittest.main()
