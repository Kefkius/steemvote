# Changelog

## v0.2.0

* Voting power is tracked. The config key `"min_voting_power"` is used to specify
    the minimum remaining voting power that your account must have for
    steemvoter to vote (Default: `90%`). Current voting power is updated via RPC every 20 seconds.
* A new config key, `"backup_author_names"`, is used to specify authors that
    should be voted for when steemvoter is not using enough voting power.
* A new config key, `"max_voting_power"`, is used to specify the remaining voting power
    above which steemvoter will vote for backup authors.
* A new config key, `"vote_interval"`, is used to specify the timespan that
    steemvoter will wait between collecting and voting on eligible comments (Default: `10 seconds`).
* The config key `"vote_delay"` is now `"min_post_age"`. The effect is the same.
    Configurations that still use `"vote_delay"` are backwards-compatible.
* Configuration info is output when steemvoter starts up.
