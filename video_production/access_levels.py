"""Video Production access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py video_production
"""

APP_NAME = 'Video Production'
PREFIX = 'vp'
CATEGORY = 'module_category_video_production'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

_PRODUCTION_OWNERS = ['producer_id', 'editor_id', 'thumbnail_artist_id']
_ON_PRODUCTION = ['production_id.%s' % field for field in ['create_uid'] + _PRODUCTION_OWNERS]

MODELS = [
    ('idea', 'Video Ideas', OPERATIONAL, ['model_video_idea'], ['author_id']),
    ('production', 'Video Productions', OPERATIONAL, ['model_video_production'], _PRODUCTION_OWNERS),
    ('script', 'Video Scripts', OPERATIONAL, ['model_video_script'],
     ['author_id', 'reviewer_id', 'approved_by_id'] + _ON_PRODUCTION),
    ('shoot', 'Video Shoots', OPERATIONAL, {
        'model_video_shoot': ['crew_ids.user_id'] + _ON_PRODUCTION,
        'model_video_shoot_crew': ['user_id', 'shoot_id.create_uid'],
        'model_video_shoot_equipment': ['shoot_id.create_uid', 'shoot_id.crew_ids.user_id'],
    }, []),
    ('edit_job', 'Edit Jobs', OPERATIONAL, {
        'model_video_edit_job': ['editor_id'] + _ON_PRODUCTION,
        'model_video_edit_version': ['submitted_by_id', 'edit_job_id.editor_id', 'edit_job_id.create_uid'],
    }, []),
    ('review', 'Reviews & Approvals', OPERATIONAL, {
        'model_video_review': ['request_owner_id', 'approver_ids.user_id'] + _ON_PRODUCTION,
        'model_video_review_approver': ['user_id', 'review_id.request_owner_id', 'review_id.create_uid'],
    }, []),
    ('metadata', 'Video Metadata', OPERATIONAL, ['model_video_metadata'], _ON_PRODUCTION),
    ('idea_stage', 'Idea Stages', CONFIG, ['model_video_idea_stage'], []),
    ('idea_tag', 'Idea Tags', CONFIG, ['model_video_idea_tag'], []),
    ('production_stage', 'Production Stages', CONFIG, ['model_video_production_stage'], []),
    ('production_tag', 'Production Tags', CONFIG, ['model_video_production_tag'], []),
    ('platform', 'Publishing Platforms', CONFIG,
     ['model_video_platform', 'model_video_platform_channel', 'model_video_platform_playlist'], []),
]

EXTRA_ACCESS = [
    ('access_video_approve_wizard', 'model_video_approve_wizard', 'group_vp_review_view', 'rwcu'),
    ('access_teleprompter_send_wizard', 'model_teleprompter_send_wizard', 'group_vp_script_view', 'rwcu'),
    ('access_video_idea_ai_wizard', 'model_video_idea_ai_wizard', 'group_vp_idea_view', 'rwcu'),
    ('access_video_metadata_seo_wizard', 'model_video_metadata_seo_wizard', 'group_vp_metadata_view', 'rwcu'),
]
