//
//  Copyright (c) 2019 Open Whisper Systems. All rights reserved.
//

#import "TSThread.h"

NS_ASSUME_NONNULL_BEGIN

@class SignalServiceAddress;

@interface TSContactThread : TSThread

// --- CODE GENERATION MARKER

// This snippet is generated by /Scripts/sds_codegen/sds_generate.py. Do not manually edit it, instead run `sds_codegen.sh`.

// clang-format off

- (instancetype)initWithUniqueId:(NSString *)uniqueId
                    archivalDate:(nullable NSDate *)archivalDate
       archivedAsOfMessageSortId:(nullable NSNumber *)archivedAsOfMessageSortId
           conversationColorName:(ConversationColorName)conversationColorName
                    creationDate:(nullable NSDate *)creationDate
isArchivedByLegacyTimestampForSorting:(BOOL)isArchivedByLegacyTimestampForSorting
                 lastMessageDate:(nullable NSDate *)lastMessageDate
                    messageDraft:(nullable NSString *)messageDraft
                  mutedUntilDate:(nullable NSDate *)mutedUntilDate
                           rowId:(int64_t)rowId
           shouldThreadBeVisible:(BOOL)shouldThreadBeVisible
              contactPhoneNumber:(nullable NSString *)contactPhoneNumber
      contactThreadSchemaVersion:(NSUInteger)contactThreadSchemaVersion
                     contactUUID:(nullable NSString *)contactUUID
              hasDismissedOffers:(BOOL)hasDismissedOffers
NS_SWIFT_NAME(init(uniqueId:archivalDate:archivedAsOfMessageSortId:conversationColorName:creationDate:isArchivedByLegacyTimestampForSorting:lastMessageDate:messageDraft:mutedUntilDate:rowId:shouldThreadBeVisible:contactPhoneNumber:contactThreadSchemaVersion:contactUUID:hasDismissedOffers:));

// clang-format on

// --- CODE GENERATION MARKER

// TODO: We might want to make this initializer private once we
//       convert getOrCreateThreadWithContactAddress to take "any" transaction.
- (instancetype)initWithContactAddress:(SignalServiceAddress *)contactAddress;

@property (nonatomic, readonly) SignalServiceAddress *contactAddress;

@property (nonatomic) BOOL hasDismissedOffers;

+ (instancetype)getOrCreateThreadWithContactAddress:(SignalServiceAddress *)contactAddress
    NS_SWIFT_NAME(getOrCreateThread(contactAddress:));

+ (instancetype)getOrCreateThreadWithContactAddress:(SignalServiceAddress *)contactAddress
                                        transaction:(SDSAnyWriteTransaction *)transaction;

// Unlike getOrCreateThreadWithContactAddress, this will _NOT_ create a thread if one does not already exist.
+ (nullable instancetype)getThreadWithContactAddress:(SignalServiceAddress *)contactAddress
                                         transaction:(SDSAnyReadTransaction *)transaction;

+ (nullable SignalServiceAddress *)contactAddressFromThreadId:(NSString *)threadId
                                                  transaction:(SDSAnyReadTransaction *)transaction;

// This is only ever used from migration from a pre-UUID world to a UUID world
+ (nullable NSString *)legacyContactPhoneNumberFromThreadId:(NSString *)threadId;

// This method can be used to get the conversation color for a given
// recipient without using a read/write transaction to create a
// contact thread.
+ (NSString *)conversationColorNameForContactAddress:(SignalServiceAddress *)address
                                         transaction:(SDSAnyReadTransaction *)transaction;

@end

NS_ASSUME_NONNULL_END
