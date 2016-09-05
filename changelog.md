# Changelog

## v0.3.0

* There is now a graphical interface. The GUI is used unless
    the option `-t` or `--terminal` is passed to steemvoter.
    Steemvoter can still be used without installing PyQt4 by passing this option.
* The database uses a new, versioned scheme.
    Steemvoter will destroy old databases that do not use the new scheme.
* Delegates can now be specified with the `delegates` config key.
    Steemvoter will track and vote for comments that your delegates vote for
    as if they were written by your specified authors.
* Backup authors have been refactored into a per-author priority system.
    Steemvoter will convert your list of backup authors into low-priority
    authors and add them to your main authors list.
* The config keys `priority_high`, `priority_normal`, and `priority_low` are
    used to specify the remaining voting power you must have to vote for
    comments of each priority.
* Steemvoter will replace the config key `max_voting_power` with `priority_low`.
* Steemvoter will replace the config key `min_voting_power` with `priority_high`.

## v0.2.0

* Voting power is tracked. The config key `"min_voting_power"` is used to specify
    the minimum remaining voting power that your account must have for
    steemvoter to vote (Default: `90%`). Current voting power is updated via RPC every 20 seconds.
* A new config key, `"backup_authors"`, is used to specify authors that
    should be voted for when steemvoter is not using enough voting power.
* A new config key, `"max_voting_power"`, is used to specify the remaining voting power
    above which steemvoter will vote for backup authors.
* A new config key, `"vote_interval"`, is used to specify the timespan that
    steemvoter will wait between collecting and voting on eligible comments (Default: `10 seconds`).
* The config key `"vote_delay"` is now `"min_post_age"`. The effect is the same.
    Configurations that still use `"vote_delay"` are backwards-compatible.
* Configuration info is output when steemvoter starts up.
* In the `"authors"` and `"backup_authors"` config lists, a string representing an author name can be used
    instead of an object. In this case, the default values will be used for optional attributes.
